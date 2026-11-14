"""Paradox MG6250 panel support (encrypted link)

Login, labels (zones, keypads, repeaters, sirens, users, partitions, outputs),
the panel clock, battery and AC voltage, zone open/bypassed/alarm and partition
exit delay/armed (stay, sleep or full)/alarm as status (the alarm bits are
provisional), arm / arm stay / arm sleep / disarm of partitions 1 and 2, zone
bypass and definition, and output on / off / release. Other controls are not
implemented.
"""

import asyncio
import collections
import datetime
import json
import logging
import os
import time
import typing

from construct import (
    Adapter,
    Bytes,
    Checksum,
    Const,
    ConstructError,
    Container,
    FixedSized,
    FocusedSeq,
    GreedyBytes,
    GreedyRange,
    Int8ub,
    Int16ub,
    Int16ul,
    Optional,
    Int32ul,
    Prefixed,
    RawCopy,
    Rebuild,
    Struct,
    Terminated,
    len_,
    this,
)

from paradox.config import config as cfg, get_limits_for_type
from paradox.connections.serial.encryption import make_serial_key
from paradox.connections.serial.mg6250_framing import (
    CHECKSUM_LEN,
    OVERHEAD,
    MG6250SerialFramer,
    crc16_modbus,
)
from paradox.exceptions import AuthenticationFailed, StatusRequestException
from paradox.lib import ps
from paradox.lib.crypto import decrypt as paradox_decrypt, encrypt as paradox_encrypt
from paradox.lib.handlers import Handler

from ..panel import Panel as PanelBase
from .event import event_map
from .property import property_map

logger = logging.getLogger("PAI").getChild(__name__)

# ---------------------------------------------------------------------------
# Commands (frame bytes 1-2, LE16)
# ---------------------------------------------------------------------------
CMD_IDENTIFY = 0x00  # panel info, then a list that may be supported commands
CMD_LOGIN = 0x01  # login with the PW_BLOCK credential (cleartext)
CMD_DATA = 0x24  # AES-encrypted record protocol (post-login)

# Session id at the start of the body.
SESSION_IDENTIFY = (0x01, 0x02)
SESSION_LOGIN = 0x02
# cmd 0x01 with session id 01 instead of 02 is the logout: selector | mode, the
# reply is 00 | selector | mode (captures/refresh-disconnect). Without it the
# panel answers every login with 0x05 busy until a power cycle.
SESSION_LOGOUT = 0x01

LOGIN_STATUS = {
    0x00: "accepted",
    0x05: "busy (previous session still open)",
    0x81: "rejected: unknown session id",
    0x83: "rejected: unknown user",
    0x84: "rejected: bad PW_BLOCK credential",
    0x85: "busy (previous session still open)",
}
LOGIN_BUSY = (0x05, 0x85)

# PW_BLOCK = header | client field(8) | len(pw) | credential(32) | trailer
PW_HEADER = bytes.fromhex("5a0101")
PW_TRAILER = bytes.fromhex("02000100")
DEFAULT_CLIENT_FIELD = bytes.fromhex("0800112233444099")

Frame = Struct(
    "fields"
    / RawCopy(
        Struct(
            "sof" / Const(0xDE, Int8ub),
            "command" / Int16ul,
            "length"
            / Rebuild(
                Int16ul,
                lambda ctx: OVERHEAD
                + len(ctx.field_a)
                + len(ctx.field_b)
                + 1
                + len(ctx.payload),
            ),
            "field_a_length" / Rebuild(Int8ub, len_(this.field_a)),
            "field_b_length" / Rebuild(Int8ub, len_(this.field_b)),
            "field_a" / Bytes(this.field_a_length),
            "field_b" / Bytes(this.field_b_length),
            "session_id" / Int8ub,
            "payload"
            / Bytes(
                this.length - OVERHEAD - this.field_a_length - this.field_b_length - 1
            ),
        )
    ),
    "checksum" / Checksum(Bytes(CHECKSUM_LEN), crc16_modbus, this.fields.data),
)

# Decrypted login reply
LoginResponse = Struct(
    "selector" / Int8ub,
    "mode" / Int8ub,
    "session_key" / Bytes(16),
    "_unknown0" / Bytes(5),
    "label" / Bytes(16),
    "_unknown1" / Bytes(2),
    "padding" / GreedyBytes,
)

PAD = 0xEE  # Paradox padding byte

# ---------------------------------------------------------------------------
# Record protocol (cmd 0x24)
#
# payload = mode | AES(header, 16) | has_data | pad | AES(data)
# has_data = 0 (an ack) ends the payload. The host ACKs every panel data
# fragment and vice versa; a reply ends at the fragment with LAST_FRAGMENT.
# ---------------------------------------------------------------------------
DataHeader = Struct(
    "tid" / Int8ub,
    "_reserved0" / Int8ub,
    "fragment" / Int16ul,
    "kind" / Int8ub,
    "service" / Int8ub,
    "_reserved1" / Int8ub,
    "selector" / Int8ub,
    "mode" / Int8ub,
)

KIND_DATA = 0x40
KIND_ACK = 0x80
# BabyWare's answer to a reply the panel sends again, in place of has_data
# (arm-bypass-disarm): the panel stops resending after it.
KIND_ACK_REPEAT = 0x88
ACK_REPEAT_FLAG = b"\x02"
ACKED_KEPT = 8  # recent reply fragments to recognise when they come back
LAST_FRAGMENT = 0x8000
# The panel drops a request sent right after our last ack (live test: every
# such request needed a retry). BabyWare waits at least 60 ms.
ACK_GAP = 0.1

SERVICE_OBJECTS = 0x17  # read/write configuration objects
SERVICE_CONTROL = 0x18  # actions: arm, disarm
SERVICE_PROGRAMMING = 0x1A  # brackets every write
SERVICE_EVENT_LOG = 0x22
OP_READ = 0x00
OP_WRITE = 0x01
OP_SET_TIME = 0x05  # clock write, laid out like a write record

# Service 0x1a, as BabyWare around a write (3c00: maybe a 60 s timeout). The
# replies echo the first 8 bytes, then 2 status bytes (00 00 = done).
PROGRAMMING_BEGIN = bytes.fromhex("00000000ffffffff3c00")
PROGRAMMING_END = bytes.fromhex("01000000ffffffff")
PROGRAMMING_STATUS = slice(8, 10)
WRITE_STATUS = slice(6, 8)  # in the reply record
# s between the write and End (BabyWare: 1 s for the clock, 0.3-0.5 s for zones)
WRITE_SETTLE = 1
# s before trying the clock again after a lost reply: the core asks at every
# poll while the clock is off, and each try opens a programming session
SET_TIME_RETRY = 600

# Service 0x18 request: prefix | panel serial | action | target number | tail.
# The first prefix byte is the target type: 00 partition, 01 zone, 03 PGM.
# The reply echoes prefix and serial, then 3 status bytes (00 00 00 = done).
# One capture per action (arm-sleep-09, arm-full-09, stay); stay arm and
# disarm of partitions 1 and 2 in long-tid-wrapped-many-operations.
PARTITION_ACTIONS = {"disarm": 0x10, "arm_stay": 0x11, "arm_sleep": 0x12, "arm": 0x13}
CONTROL_PREFIX = b"\x00\xff" + bytes(5)
CONTROL_TAIL = bytes.fromhex("0001000000")  # the same in every capture
# long-tid-wrapped-many-operations: BabyWare's Activate, Deactivate and Release
# on PGM 1 then 2 sent 02, 01, 03, in that order.
CONTROL_PGM_PREFIX = b"\x03\xff" + bytes(5)
CONTROL_PGM_TAIL = bytes.fromhex("0001") + bytes(10)
PGM_ACTIONS = {"on": 0x02, "off": 0x01, "release": 0x03}
PGM_PULSE = "pulse"  # on, cfg.OUTPUT_PULSE_DURATION, off
# captures/bypass: 01 sets and 00 clears, not a toggle; the target is the zone
CONTROL_ZONE_PREFIX = b"\x01\xff" + bytes(5)
ZONE_ACTIONS = {"bypass": 0x01, "clear_bypass": 0x00}
# Zone command "definition_<name or number>" (e.g. definition_instant) writes
# the zone definition, as BabyWare (captures/send-zone-sleep: zone 14 from 10
# to 9; change-zone: zones 4-7).
ZONE_DEFINITION_COMMAND = "definition_"
CONTROL_OK = bytes(3)
PARTITIONS = [1, 2]  # 2 only with section [2000] option 7, see load_labels
IDENTIFY_SERIAL = slice(8, 12)  # panel serial in the first identify reply

# Objects (big-endian ids), with the index count BabyWare reads
OBJ_ZONE = 0x0001
OBJ_KEYPAD = 0x0009
OBJ_REPEATER = 0x000B
OBJ_SIREN = 0x000D
OBJ_PGM = 0x0005  # field 1 label ("Output 01")
PGM_COUNT = 8
# Field 1: one byte per section from [2000] on, option 1 = bit 0 (55 87 12 fe
# ...). BabyWare wrote 15 <-> 55 to disable / enable area 2.
OBJ_SETTINGS = 0x0017
SETTINGS_FIELD_OPTIONS = 1
OPTION_TWO_PARTITIONS = 0x40  # [2000] option 7
OBJ_SYSTEM = 0x001C
OBJ_ZONE_STATUS = 0x001E
OBJ_CLOCK = 0x0024
OBJ_PARTITION_STATUS = 0x0025
# From BabyWare's "Receive all Programming" (captures/receive-all-*)
OBJ_USER = 0x0007  # field 1 label; field 4 is the code, not read
USER_COUNT = 16
OBJ_AREA = 0x001A  # partitions; field 1 byte 0 = exit delay (s)
AREA_FIELD_LABEL = 2  # 16 bytes

FIELD_SERIAL = 0  # 6 bytes, all zero when nothing is enrolled (not for zones)
FIELD_LABEL = 1  # 16 bytes
# Zone field 0: device (2) | definition | partition | options | ?. An empty
# zone reads 00 00 00 01 87 00. change-zone: BabyWare wrote definition
# 09 -> 08 for zones 4-7.
ZONE_DEFINITION = 2
ZONE_PARTITION = 3  # 1, 2 or 3 = both
# Programming guide table 4, with the names of the SP/MG definitions where
# they are the same (0-26). 0 (disabled) can not be written: PAI would lose
# the zone.
ZONE_DEFINITIONS = {
    0: "disabled",
    1: "delay_1",
    2: "delay_2",
    3: "entry_delay_1_full",
    4: "entry_delay_2_full",
    5: "follow",
    6: "follow_sleep_full",
    7: "follow_full",
    8: "instant",
    9: "instant_sleep_full",
    10: "instant_full",
    11: "instant_fire",
    12: "delayed_fire",
    13: "instant_fire_silent",
    14: "delayed_fire_silent",
    15: "buzzer_24h",
    16: "burglary_24h",
    17: "hold_up_24h",
    18: "gas_24hr",
    19: "heat_24h",
    20: "water_24h",
    21: "freeze_24h",
    22: "panic_24h",
    23: "follow_no_pre_alarm",
    24: "instant_no_pre_alarm",
    25: "keyswitch_maintain",
    26: "keyswitch_momentary",
    27: "entry_delay_1_sleep_full",
    28: "entry_delay_2_sleep_full",
    29: "unarmed",
    33: "custom_1",
    34: "custom_2",
    35: "custom_3",
    36: "custom_4",
}
ZONE_DEFINITION_NUMBERS = {name: n for n, name in ZONE_DEFINITIONS.items()}
CLOCK_FIELDS = (0, 1, 2, 3)  # BabyWare's selection; field 1 is the date
CLOCK_FIELD_DATE = 1  # century, year, month, day, hour, minute
# battery | AC | unknown, one byte each. BabyWare showed Battery 5.3 V and AC
# 0.0 for 42 00 0c: 0.08 V per step (20.4 V full scale). On mains with the
# 7.5 V adapter the AC byte is 0x5f and BabyWare shows 7.5 V (2026-11-11): a
# little less per step, from this one point.
CLOCK_FIELD_POWER = 2
VOLTS_PER_STEP = 0.08
AC_VOLTS_PER_STEP = 0.079
SYSTEM_FIELDS = (0, 1)  # what BabyWare polls every 20 s
SYSTEM_FIELD_STATUS = 1  # byte 0: counter, changes when a zone does
# byte 0: 0x20 bypassed (long-tid-wrapped-many-operations: 20 from BabyWare's
# bypass to its clear), any other bit = open (01; 04 on the zone in alarm);
# byte 1: flags below; byte 2: 0x04 during the exit delay of partition 2
ZONE_STATUS_FIELD = 0
ZONE_BYPASSED = 0x20
# Provisional, from one alarm capture (and set-sms for the memory flag).
# Zone status byte 1: 0x04 on every zone during the exit delay (not used),
# 0x10 on the zone in alarm, 0x20 alarm in memory (stays once closed).
ZONE_IN_ALARM = 0x10
ZONE_ALARM_MEMORY = 0x20
# Partition status field 0: state | flags | flags | 3 unknown. Index 1-2 =
# partition 1-2, same layout (area 2: 01 00 01 then 05 00 00 on a stay arm). Seen:
# disarmed 00 00 00; exit delay 01 / 02 / 03 00 01 and armed 05 / 06 / 07
# 00 00 for stay / sleep / full arm; alarm (full arm) 77 02 40. Provisional,
# second byte: 10 armed with a zone open (the plain arm command, no force
# command seen), as 03 10 01 then 07 10 00.
PARTITION_STATUS_FIELD = 0
PARTITION_MODE = 0x03  # state byte: arm mode, set from the arm on
PARTITION_STAY, PARTITION_SLEEP, PARTITION_FULL = 0x01, 0x02, 0x03
PARTITION_ARMED = 0x04  # state byte, once the exit delay is over
PARTITION_ALARM = 0x70  # state byte, all three set in the one alarm seen
PARTITION_EXIT_DELAY = 0x01  # third byte
PARTITION_FORCED = 0x10  # second byte

LABEL_OBJECTS = {
    "zone": (OBJ_ZONE, 64),
    "keypad": (OBJ_KEYPAD, 4),
    "repeater": (OBJ_REPEATER, 4),
    "siren": (OBJ_SIREN, 4),
}
READ_BATCH = 8  # objects per request, keeps the request in one frame

ReadRecordRequest = Struct(
    "op" / Const(OP_READ, Int8ub),
    "length" / Rebuild(Int8ub, 7 + 2 * len_(this.fields)),
    "obj" / Int16ub,
    "index" / Int16ub,
    "reserved" / Const(0, Int8ub),
    "fields"
    / GreedyRange(
        Struct(
            "id" / Int8ub,
            "reserved" / Const(0, Int8ub),
        )
    ),
)

# Event log (service 0x22), records: op | len | ..., numbers are LE32
# range request 01: 00 01 01 | first | ff ff ff ff
# range reply   01: 5 status | first | last | count
# read request  00: 00 01 01 | first | last | 00 00 00 00
# read reply    00: 5 status | first | last | count | events (per fragment)
# event: number | 1f | major | minor | area | century year month day hour minute
#        | 5 unknown | label type | label (16)
LOG_OP_READ = 0x00
LOG_OP_RANGE = 0x01
LOG_REQUEST = b"\x00\x01\x01"
LOG_ANY = 0xFFFFFFFF
LOG_REPLY_HEADER = 7
LOG_EVENT_LEN = 36
LogRecord = Struct(
    "op" / Int8ub,
    "len" / Int8ub,
    "_status" / Bytes(5),
    "first" / Int32ul,
    "last" / Int32ul,
    "count" / Int32ul,
)
LogEvent = Struct(
    "number" / Int32ul,
    "_unknown0" / Bytes(1),
    "major" / Int8ub,
    "minor" / Int8ub,
    "area" / Int8ub,
    "date" / Bytes(6),
    "_unknown1" / Bytes(5),
    "label_type" / Int8ub,
    "label" / Bytes(16),
)


def build_log_request(op: int, first: int, last: int = LOG_ANY) -> bytes:
    """A range (op 01) or read (op 00) request of the event log."""
    trailer = b"" if op == LOG_OP_RANGE else bytes(4)
    data = (
        LOG_REQUEST + first.to_bytes(4, "little") + last.to_bytes(4, "little") + trailer
    )
    return bytes([op, len(data) + 2]) + data


def parse_log_records(data: bytes) -> typing.List[Container]:
    """Records of a reply fragment: Container(op, first, last, count, events)."""
    records = []
    i = 0
    while i + 2 <= len(data) and data[i] != PAD and data[i + 1] >= 2:
        length = data[i + 1]
        raw = data[i : i + length]
        i += length
        if len(raw) < length or len(raw) < LogRecord.sizeof():
            continue
        record = LogRecord.parse(raw)
        events = raw[LogRecord.sizeof() :]
        record.events = [
            LogEvent.parse(events[j : j + LOG_EVENT_LEN])
            for j in range(0, len(events) - LOG_EVENT_LEN + 1, LOG_EVENT_LEN)
        ]
        records.append(record)
    return records


def build_write_record(
    obj: int, index: int, field: int, value: bytes, op: int = OP_WRITE
) -> bytes:
    """op | len | obj (BE16) | index (BE16) | 00 | field | len (BE16) | value"""
    body = (
        obj.to_bytes(2, "big")
        + index.to_bytes(2, "big")
        + b"\x00"
        + bytes([field])
        + len(value).to_bytes(2, "big")
        + value
    )
    return bytes([op, 2 + len(body)]) + body


def build_set_time_record(now: datetime.datetime) -> bytes:
    date = bytes(
        [now.year // 100, now.year % 100, now.month, now.day, now.hour, now.minute]
    )
    return build_write_record(OBJ_CLOCK, 1, CLOCK_FIELD_DATE, date, OP_SET_TIME)


def build_read_record(obj: int, index: int, fields: typing.Iterable[int]) -> bytes:
    return ReadRecordRequest.build(
        {
            "obj": obj,
            "index": index,
            "fields": [{"id": field} for field in fields],
        }
    )


class FieldsAdapter(Adapter):
    """List of field TLVs -> {id: value} (parse only)."""

    def _decode(self, obj, context, path):
        return {f.id: f.value for f in obj}


RecordField = Struct(
    "id" / Int8ub,
    "status" / Const(0, Int8ub),
    "value" / Prefixed(Int16ub, GreedyBytes),
)

RECORD_HEADER_LEN = 8

# The length byte covers the whole record, op and length included.
Record = Struct(
    "op" / Int8ub,
    "length" / Int8ub,
    "obj" / Int16ub,
    "index" / Int16ub,
    "status" / Const(bytes(2)),
    "fields"
    / FieldsAdapter(
        FixedSized(
            this.length - RECORD_HEADER_LEN,
            FocusedSeq("fields", "fields" / GreedyRange(RecordField), Terminated),
        )
    ),
)

# Captures end with a zero terminator before padding; some have no padding.
Records = FocusedSeq(
    "records",
    "records" / GreedyRange(Record),
    Optional(Const(b"\x00")),
    GreedyRange(Const(PAD, Int8ub)),
    Terminated,
)


def parse_records(data: bytes) -> typing.List[Container]:
    """Split a reply into records, decoding the field TLVs of each.

    record = op | len | obj (BE16) | index (BE16) | status (2) | fields...
    field  = id | status | len (BE16) | value
    """
    try:
        return Records.parse(data)
    except ConstructError as exc:
        raise StatusRequestException("MG6250: invalid record reply") from exc


def decode_date(raw: bytes) -> typing.Optional[datetime.datetime]:
    if len(raw) < 6 or raw[2] == 0:
        return None
    return datetime.datetime(raw[0] * 100 + raw[1], *raw[2:6])


def limited_indexes(elem_type: str, indexes: typing.Iterable[int]) -> typing.List[int]:
    """Keep the indexes cfg.LIMITS allows, like the other panels: configured
    indexes this panel does not have are ignored, not read."""
    limits = get_limits_for_type(elem_type)
    return [i for i in indexes if limits is None or i in limits]


def credential_block(password: typing.Union[str, bytes, int]) -> bytes:
    """32-byte credential: make_serial_key(pw) encrypted under itself."""
    key = make_serial_key(password)
    return paradox_encrypt(key, key)


def build_pw_block(
    password: typing.Union[str, bytes, int, None],
    client_field: bytes = DEFAULT_CLIENT_FIELD,
) -> bytes:
    if password is None:
        raise AuthenticationFailed("Set PASSWORD to the MG6250 PC password")
    if isinstance(password, int):
        password = str(password).zfill(4)
    if isinstance(password, str):
        password = password.encode("utf-8")
    if not 1 <= len(password) <= 255:
        raise AuthenticationFailed("MG6250 PASSWORD must contain 1 to 255 bytes")
    return (
        PW_HEADER
        + client_field
        + bytes([len(password)])
        + credential_block(password)
        + PW_TRAILER
    )


def build_frame(command: int, session_id: int, payload: bytes = b"") -> bytes:
    return Frame.build(
        {
            "fields": {
                "value": {
                    "command": command,
                    "field_a": b"",
                    "field_b": b"",
                    "session_id": session_id,
                    "payload": payload,
                }
            }
        }
    )


class PanelAckHandler(Handler):
    """Consumes the session's frames, so the core does not warn about them: the
    panel's acks of our requests, and replies nobody waits for any more, which it
    sends again when a request was retried or an ack was late."""

    NAME = "MG6250 panel ack"

    def __init__(self, panel):
        super().__init__(name=self.NAME)
        self.panel = panel

    def can_handle(self, data) -> bool:
        return self.panel.is_session_frame(data)

    async def __call__(self, data):
        self.panel.answer_repeated_reply(data)


class Panel(PanelBase):
    event_map = event_map
    property_map = property_map
    status_request_addresses = [0]

    def __init__(
        self, core, start_communication_response=None, variable_message_length=False
    ):
        super().__init__(core, variable_message_length)
        # The MG6250 ignores StartCommunication (0x5F), so connect() passes the
        # InitiateCommunication (0x72) reply here instead.
        if start_communication_response is not None:
            self.settings = start_communication_response.fields.value
        self.session = None  # LoginResponse once logged in
        self.session_key = None  # 16-byte AES key for cmd 0x24 traffic
        self._tid = 0
        self._transaction_lock = None
        self._zones = []  # enrolled zones, set by load_labels before polling
        self._partitions = PARTITIONS[:1]  # set by load_labels
        self._zone_partitions = {}  # {zone: partition byte}, from load_labels
        # {zone: definition byte}, from load_labels and our own writes: a
        # change made in BabyWare shows after a restart only
        self._zone_definitions = {}
        self._log_enabled = False  # read the event log, set once logged in
        self._set_time_refused = False  # do not try again on this connection
        self._set_time_retry_at = 0.0  # time.monotonic() of the next try
        self._acked = collections.deque(maxlen=ACKED_KEPT)  # (tid, fragment)
        self._log_last = None  # number of the last event published
        self._change_counter = None  # last object 0x1c counter seen
        # read when the counter changes: {zone: field 0}, {partition: field 0}
        self._zone_status = None
        self._partition_status = None
        self.panel_serial = None  # 4 bytes from identify, sent with each action

    def build_data_frame(self, payload: bytes) -> bytes:
        """A 0x24 frame tagged with the session id the login reply assigned."""
        if self.session is None:
            raise RuntimeError("no session; log in first")
        return build_frame(
            CMD_DATA, self.session.selector, bytes([self.session.mode]) + payload
        )

    def _encrypted_header(self, tid, fragment, kind, service) -> bytes:
        header = DataHeader.build(
            {
                "tid": tid,
                "_reserved0": 0,
                "fragment": fragment,
                "kind": kind,
                "service": service,
                "_reserved1": 0,
                "selector": self.session.selector,
                "mode": self.session.mode,
            }
        )
        return paradox_encrypt(header, self.session_key)

    def build_request(self, tid: int, service: int, data: bytes) -> bytes:
        """A single-fragment request carrying `data`."""
        header = self._encrypted_header(tid, LAST_FRAGMENT | 1, KIND_DATA, service)
        pad = -len(data) % 16
        return self.build_data_frame(
            header + bytes([1, pad]) + paradox_encrypt(data, self.session_key)
        )

    def build_ack_repeat(self, tid: int, fragment: int, service: int) -> bytes:
        header = self._encrypted_header(tid, fragment, KIND_ACK_REPEAT, service)
        return self.build_data_frame(header + ACK_REPEAT_FLAG)

    def build_ack(self, tid: int, fragment: int, service: int) -> bytes:
        header = self._encrypted_header(tid, fragment, KIND_ACK, service)
        return self.build_data_frame(header + b"\x00")

    def make_framer(self):
        return MG6250SerialFramer()

    def parse_message(self, message, direction="topanel") -> typing.Optional[Container]:
        # Legacy identify (0x72) is still handled by the base.
        parent = super().parse_message(message, direction)
        if parent is not None:
            return parent
        if message and message[0] == 0xDE:
            return Frame.parse(message)
        return None

    def decrypt_data(self, payload: bytes):
        """Decrypt a cmd 0x24 payload -> (header, data), data None for an ack."""
        if self.session_key is None:
            raise RuntimeError("no session key; log in first")
        body = payload[1:]  # skip the mode byte (second session id byte)
        header = DataHeader.parse(paradox_decrypt(body[:16], self.session_key))
        if len(body) < 18 or not body[16]:
            return header, None
        # body[17] counts the padding; parse_records stops on it instead, as
        # the panel's count is sometimes one more than the 0xEE bytes sent.
        return header, paradox_decrypt(body[18:], self.session_key)

    def _decrypt_message(self, message):
        """(header, data) of a cmd 0x24 message, None for anything else."""
        fields = message.fields.value
        if (
            self.session_key is None
            or fields.get("command") != CMD_DATA
            or len(fields.payload) < 17
        ):
            return None
        return self.decrypt_data(bytes(fields.payload))

    def _is_reply(self, message, tid: int, service: int) -> bool:
        decrypted = self._decrypt_message(message)
        if decrypted is None:
            return False
        header, data = decrypted
        return (
            data is not None
            and header.kind == KIND_DATA
            and header.tid == tid
            and header.service == service
        )

    def is_session_frame(self, message) -> bool:
        return self._decrypt_message(message) is not None

    def answer_repeated_reply(self, message) -> None:
        """Ack again a reply fragment that was already acked."""
        header, data = self._decrypt_message(message)
        if data is None or header.kind != KIND_DATA:
            return
        if (header.tid, header.fragment) in self._acked:
            logger.debug("MG6250: repeated reply to request %d", header.tid)
            self.core.connection.write(
                self.build_ack_repeat(header.tid, header.fragment, header.service)
            )

    async def transact(self, service: int, data: bytes) -> typing.List[bytes]:
        """Send one request, ACK each reply fragment, return their data.

        Each fragment is padded on its own, so parse them separately.
        """
        if self.session is None:
            # e.g. an MQTT command arriving while PAI reconnects
            raise StatusRequestException("MG6250: not logged in")
        if self._transaction_lock is None:
            self._transaction_lock = asyncio.Lock()
        async with self._transaction_lock:
            # A byte counter, as BabyWare's: 255 is followed by 0. Skipping 0
            # makes the panel ignore every request after the 255th.
            self._tid = (self._tid + 1) & 0xFF
            tid = self._tid
            message = self.build_request(tid, service, data)
            fragments = []
            while True:
                reply = await self.core.send_wait(
                    message=message,
                    reply_expected=lambda m: self._is_reply(m, tid, service),
                )
                if reply is None:
                    raise StatusRequestException(f"MG6250: no reply to request {tid}")
                header, reply_data = self.decrypt_data(
                    bytes(reply.fields.value.payload)
                )
                fragments.append(reply_data)
                self._acked.append((tid, header.fragment))
                message = self.build_ack(tid, header.fragment, service)
                if header.fragment & LAST_FRAGMENT:
                    # send_wait without a reply would resend it; write the ack once.
                    self.core.connection.write(message)
                    await asyncio.sleep(ACK_GAP)
                    return fragments

    async def read_records(
        self, requests: typing.Iterable[typing.Tuple[int, int, typing.Iterable[int]]]
    ) -> typing.Dict[typing.Tuple[int, int], dict]:
        """Read (obj, index, fields) -> {(obj, index): {field: value}}."""
        requests = list(requests)
        result = {}
        for start in range(0, len(requests), READ_BATCH):
            request = b"".join(
                build_read_record(obj, index, fields)
                for obj, index, fields in requests[start : start + READ_BATCH]
            )
            for fragment in await self.transact(SERVICE_OBJECTS, request):
                for record in parse_records(fragment):
                    # The panel may split one object's fields over several records.
                    if record.op == OP_READ:
                        key = (record.obj, record.index)
                        result.setdefault(key, {}).update(record.fields)
        return result

    async def read_objects(
        self, obj: int, indexes: typing.Iterable[int], fields: typing.Iterable[int]
    ) -> typing.Dict[int, dict]:
        """Read `fields` of each object index -> {index: {field: value}}."""
        fields = list(fields)
        records = await self.read_records([(obj, i, fields) for i in indexes])
        return {index: f for (o, index), f in records.items() if o == obj}

    async def initialize_communication(self, password) -> bool:
        """Identify, then log in with the PW_BLOCK credential.

        `password` must be set to the PC password. The username is read
        from cfg.MG6250_USERNAME (default "admin").
        """
        username = cfg.MG6250_USERNAME
        pw_block = build_pw_block(password)

        # identify (0x00) twice: model/firmware, then a list (supported commands?)
        for session_id in SESSION_IDENTIFY:
            reply = await self.core.send_wait(
                message=build_frame(CMD_IDENTIFY, session_id),
                reply_expected=lambda m: m.fields.value.command == CMD_IDENTIFY,
            )
            if reply is not None and session_id == SESSION_IDENTIFY[0]:
                serial = bytes(reply.fields.value.payload)[IDENTIFY_SERIAL]
                if len(serial) == 4:
                    self.panel_serial = serial

        # credential + length use the PC password; the username is appended.
        u = username.encode()
        login = build_frame(CMD_LOGIN, SESSION_LOGIN, pw_block + bytes([len(u)]) + u)
        reply = await self.core.send_wait(
            message=login, reply_expected=lambda m: m.fields.value.command == CMD_LOGIN
        )
        if reply is None:
            logger.error("MG6250 login: no reply")
            return False

        status = bytes(reply.fields.value.payload)[:1]
        logger.info(
            "MG6250 login status 0x%02x (%s)",
            status[0],
            LOGIN_STATUS.get(status[0], "unknown"),
        )
        if status[0] in LOGIN_BUSY:
            # The panel keeps the last session (PAI, BabyWare) open until it
            # times out. Through a serial bridge it never sees PAI go away, so
            # that session may be ours: try it, else the main loop retries.
            if await self._resume_session():
                return True
            logger.warning("MG6250 login: panel busy, will retry")
            return False
        if status != b"\x00":
            raise AuthenticationFailed(
                LOGIN_STATUS.get(status[0], f"status 0x{status[0]:02x}")
            )

        # decrypt the reply with make_serial_key(pw)
        self.session = self._decrypt_login_reply(
            bytes(reply.fields.value.payload), make_serial_key(password)
        )
        if self.session is None:
            logger.error("MG6250 login reply did not decrypt")
            return False
        self.session_key = self.session.session_key
        self._register_ack_handler()
        self._log_enabled = True
        logger.info(
            "MG6250 session: selector 0x%02x mode 0x%02x user %r",
            self.session.selector,
            self.session.mode,
            self.session.label.decode("ascii", "replace").rstrip(),
        )
        self._save_session()
        return True

    def close_connection(self):
        """Log out, so that the next login is not refused as busy."""
        if self.session is None:
            super().close_connection()
            return
        self.core.connection.write(
            build_frame(
                CMD_LOGIN,
                SESSION_LOGOUT,
                bytes([self.session.selector, self.session.mode]),
            )
        )
        self.session = self.session_key = None
        self._log_enabled = False
        self._forget_session()

    def _register_ack_handler(self):
        registry = self.core.connection.handler_registry
        registry.remove_by_name(PanelAckHandler.NAME)  # after a re-login
        registry.append(PanelAckHandler(self))

    def _save_session(self):
        """Keep the session in cfg.MG6250_SESSION_FILE (owner-only)."""
        path = cfg.MG6250_SESSION_FILE
        if not path:
            return
        data = {
            "selector": self.session.selector,
            "mode": self.session.mode,
            "session_key": self.session_key.hex(),
            "label": self.session.label.hex(),
        }
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
        except OSError as e:
            logger.warning("MG6250: cannot save the session to %s: %s", path, e)

    @staticmethod
    def _forget_session():
        """The saved session ended: it cannot be resumed any more."""
        path = cfg.MG6250_SESSION_FILE
        if path:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning("MG6250: cannot remove %s: %s", path, e)

    @staticmethod
    def _load_session() -> typing.Optional[Container]:
        path = cfg.MG6250_SESSION_FILE
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return Container(
                selector=int(data["selector"]),
                mode=int(data["mode"]),
                session_key=bytes.fromhex(data["session_key"]),
                label=bytes.fromhex(data.get("label", "")),
            )
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.warning("MG6250: cannot read the session from %s: %s", path, e)
            return None

    async def _resume_session(self) -> bool:
        """Use the saved session if the panel still answers it."""
        saved = self._load_session()
        if saved is None:
            return False
        self.session, self.session_key = saved, saved.session_key
        self._register_ack_handler()
        try:
            records = await self.read_records([(OBJ_SYSTEM, 1, SYSTEM_FIELDS)])
        except (StatusRequestException, asyncio.TimeoutError):
            records = {}
        if (OBJ_SYSTEM, 1) not in records:
            logger.warning("MG6250: the saved session is no longer open")
            self.session = self.session_key = None
            self._forget_session()  # do not wait on it again at the next login
            return False
        self._log_enabled = True
        logger.info(
            "MG6250: resumed the previous session (selector 0x%02x mode 0x%02x)",
            saved.selector,
            saved.mode,
        )
        return True

    @staticmethod
    def _decrypt_login_reply(payload: bytes, key: bytes):
        data = payload[1:]  # strip status byte
        missing = -len(data) % 16
        try:
            if missing == 1:
                # Some firmware encrypts a padded block but sends one byte short.
                for guess in range(256):
                    plain = paradox_decrypt(data + bytes([guess]), key)
                    if plain.endswith(bytes([PAD]) * 4):
                        return LoginResponse.parse(plain)
            # Otherwise pad with 0xEE: only the last block, past the session key, comes out garbled.
            return LoginResponse.parse(
                paradox_decrypt(data + bytes([PAD]) * missing, key)
            )
        except ConstructError:
            return None

    # -- record protocol (cmd 0x24): read-only ---------------------------
    async def load_memory(self):
        # The zone definitions come with the labels (zone field 0): one read.
        # Sent in the order of the other panels, definitions first.
        logger.info("Loading labels and definitions")
        labels = await self.load_labels()
        ps.sendMessage("definitions_loaded", data=await self.load_definitions())
        ps.sendMessage("labels_loaded", data=labels)

    async def load_definitions(self) -> dict:
        """Zone definition and partition, as the SP/MG panels: what load_labels
        read, and what was written since."""
        return {
            "zone": {
                zone: {
                    "definition": ZONE_DEFINITIONS.get(definition, definition),
                    "partition": self._zone_partitions.get(zone),
                }
                for zone, definition in sorted(self._zone_definitions.items())
            }
        }

    async def load_labels(self):
        data = {}
        for elem_type, (obj, count) in LABEL_OBJECTS.items():
            start_time = time.time()
            indexes = limited_indexes(elem_type, range(1, count + 1))
            objects = await self.read_objects(obj, indexes, (FIELD_SERIAL, FIELD_LABEL))
            elements = data[elem_type] = {}
            for index in indexes:
                fields = objects.get(index, {})
                serial = fields.get(FIELD_SERIAL, b"")
                if obj == OBJ_ZONE:
                    if len(serial) <= ZONE_DEFINITION:
                        raise StatusRequestException(
                            f"MG6250: incomplete enrollment reply for zone {index}"
                        )
                    enrolled = serial[ZONE_DEFINITION]
                else:
                    enrolled = any(serial)
                if not enrolled:
                    continue  # nothing enrolled at this index, or zone disabled
                label = self.decode_label(fields.get(FIELD_LABEL, b""))
                element = self.label_element(elem_type, index, label)
                if obj == OBJ_ZONE and len(serial) > ZONE_PARTITION:
                    self._zone_partitions[index] = serial[ZONE_PARTITION]
                if obj == OBJ_ZONE:
                    self._zone_definitions[index] = enrolled
                elements[index] = element
            self.log_labels_loaded(elem_type, elements, start_time)
        self._zones = sorted(data["zone"])

        # Users have no serial: list them all, as for the other panels.
        start_time = time.time()
        indexes = limited_indexes("user", range(1, USER_COUNT + 1))
        users = await self.read_objects(OBJ_USER, indexes, (FIELD_LABEL,))
        data["user"] = {
            index: self.label_element(
                "user", index, self.decode_label(fields.get(FIELD_LABEL, b""))
            )
            for index, fields in sorted(users.items())
        }
        self.log_labels_loaded("user", data["user"], start_time)

        # Area 2 is listed only when the panel is set for two partitions.
        start_time = time.time()
        settings = await self.read_objects(
            OBJ_SETTINGS, [1], (SETTINGS_FIELD_OPTIONS,)
        )
        options = settings.get(1, {}).get(SETTINGS_FIELD_OPTIONS, b"")
        two = bool(options) and bool(options[0] & OPTION_TWO_PARTITIONS)
        indexes = limited_indexes("partition", PARTITIONS if two else PARTITIONS[:1])
        self._partitions = indexes
        areas = await self.read_objects(OBJ_AREA, indexes, (AREA_FIELD_LABEL,))
        data["partition"] = {
            i: self.label_element(
                "partition",
                i,
                self.decode_label(areas.get(i, {}).get(AREA_FIELD_LABEL, b""))
                or f"Partition {i}",
            )
            for i in indexes
        }
        self.log_labels_loaded("partition", data["partition"], start_time)

        # No enrollment field is known for the outputs: all are listed, for
        # control only (their state is not decoded).
        start_time = time.time()
        indexes = limited_indexes("pgm", range(1, PGM_COUNT + 1))
        pgms = await self.read_objects(OBJ_PGM, indexes, (FIELD_LABEL,))
        data["pgm"] = {
            index: self.label_element(
                "pgm",
                index,
                self.decode_label(fields.get(FIELD_LABEL, b"")) or f"Output {index:02}",
            )
            for index, fields in sorted(pgms.items())
        }
        self.log_labels_loaded("pgm", data["pgm"], start_time)
        return data

    async def request_status(self, _nr) -> typing.Optional[Container]:
        """Panel clock, battery and AC voltage, zone open/alarm and partition
        exit delay/armed/alarm.

        As BabyWare does: poll the change counter (object 0x1c) every loop and
        read zone status (object 0x1e) and partition status (object 0x25)
        again only when it changes; it changes on arming and on an alarm too.
        """
        objects = await self.read_records(
            [(OBJ_SYSTEM, 1, SYSTEM_FIELDS), (OBJ_CLOCK, 1, CLOCK_FIELDS)]
        )
        clock = objects.get((OBJ_CLOCK, 1), {})
        date = clock.get(CLOCK_FIELD_DATE)
        counter = objects.get((OBJ_SYSTEM, 1), {}).get(SYSTEM_FIELD_STATUS, b"")[:1]
        if date is None or not counter:
            raise StatusRequestException("MG6250: incomplete status reply")

        counter = counter[0]
        if self._zone_status is None or counter != self._change_counter:
            records = await self.read_records(
                [(OBJ_ZONE_STATUS, i, [ZONE_STATUS_FIELD]) for i in self._zones]
                + [
                    (OBJ_PARTITION_STATUS, i, [PARTITION_STATUS_FIELD])
                    for i in self._partitions
                ]
            )
            zones = {
                index: records.get((OBJ_ZONE_STATUS, index), {}).get(
                    ZONE_STATUS_FIELD, b""
                )[:2]
                for index in self._zones
            }
            partitions = {
                index: records.get((OBJ_PARTITION_STATUS, index), {}).get(
                    PARTITION_STATUS_FIELD, b""
                )[:3]
                for index in self._partitions
            }
            if any(len(value) < 2 for value in zones.values()):
                raise StatusRequestException("MG6250: incomplete zone status reply")
            if any(len(value) < 3 for value in partitions.values()):
                raise StatusRequestException(
                    "MG6250: incomplete partition status reply"
                )
            # Commit the whole snapshot together so an incomplete read is retried.
            self._zone_status = zones
            self._partition_status = partitions
            self._change_counter = counter

        system = Container(date=Container(time=decode_date(date)))
        power = clock.get(CLOCK_FIELD_POWER, b"")
        if len(power) >= 2:
            system.power = Container(
                battery=round(power[0] * VOLTS_PER_STEP, 1),
                ac=round(power[1] * AC_VOLTS_PER_STEP, 1),
            )
        await self._publish_new_events()
        zones = self._zone_status
        partitions = self._partition_status
        return Container(
            system=system,
            zone_open={i: self._zone_open(v) for i, v in zones.items()},
            zone_bypassed={i: bool(v[0] & ZONE_BYPASSED) for i, v in zones.items()},
            zone_presently_in_alarm={
                i: bool(v[1] & ZONE_IN_ALARM) for i, v in zones.items()
            },
            zone_generated_alarm={
                i: bool(v[1] & ZONE_ALARM_MEMORY) for i, v in zones.items()
            },
            partition_arm={
                i: bool(v[0] & PARTITION_ARMED) for i, v in partitions.items()
            },
            partition_arm_stay={
                i: self._armed_in(v, PARTITION_STAY) for i, v in partitions.items()
            },
            partition_arm_sleep={
                i: self._armed_in(v, PARTITION_SLEEP) for i, v in partitions.items()
            },
            partition_arm_away={
                i: self._armed_in(v, PARTITION_FULL) for i, v in partitions.items()
            },
            partition_arm_force={
                i: bool(v[1] & PARTITION_FORCED) for i, v in partitions.items()
            },
            partition_exit_delay={
                i: bool(v[2] & PARTITION_EXIT_DELAY) for i, v in partitions.items()
            },
            partition_audible_alarm={
                i: bool(v[0] & PARTITION_ALARM) for i, v in partitions.items()
            },
            partition_ready_status={
                i: self._partition_ready(i, zones) for i in partitions
            },
        )

    @staticmethod
    def _zone_open(status: bytes) -> bool:
        return bool(status[0] & ~ZONE_BYPASSED)

    @staticmethod
    def _armed_in(status: bytes, mode: int) -> bool:
        """Armed in `mode`. The mode bits are set from the start of the exit
        delay: without the armed bit, the partition is not armed yet."""
        return bool(status[0] & PARTITION_ARMED) and (
            status[0] & PARTITION_MODE == mode
        )

    async def _log_range(self, first: int) -> typing.Optional[Container]:
        fragments = await self.transact(
            SERVICE_EVENT_LOG, build_log_request(LOG_OP_RANGE, first)
        )
        for fragment in fragments:
            for record in parse_log_records(fragment):
                if record.op == LOG_OP_RANGE:
                    return record
        return None

    async def _publish_new_events(self):
        """Publish the events added to the log since the last poll.

        BabyWare always asks from its saved position, so the first request,
        from 0, is not from a capture: if the panel refuses it, stop reading
        the log for this session rather than slow down the status polling.
        Old events are not published: they would look like new alarms.
        """
        if not self._log_enabled:
            return
        first = self._log_last or 0
        try:
            log_range = await self._log_range(first)
            if log_range is None:
                raise StatusRequestException("no range in the reply")
            if self._log_last is None:
                self._log_last = log_range.last
                logger.info("MG6250: event log at event %d", log_range.last)
                return
            if log_range.last < self._log_last:
                # Log cleared (or numbering restarted): follow it from here,
                # as on the first poll, or no event would be published until
                # the numbers pass the old position.
                logger.warning(
                    "MG6250: event log went back from event %d to %d",
                    self._log_last,
                    log_range.last,
                )
                self._log_last = log_range.last
                return
            if log_range.last == self._log_last:
                return
            first = max(self._log_last + 1, log_range.first)
            fragments = await self.transact(
                SERVICE_EVENT_LOG,
                build_log_request(LOG_OP_READ, first, log_range.last),
            )
        except (StatusRequestException, asyncio.TimeoutError) as e:
            if self._log_last is None:
                logger.warning("MG6250: not reading the event log: %s", e)
                self._log_enabled = False
            else:
                logger.debug("MG6250: event log read failed: %s", e)
            return
        events = [
            event
            for fragment in fragments
            for record in parse_log_records(fragment)
            if record.op == LOG_OP_READ
            for event in record.events
            if event.number > self._log_last
        ]
        for event in sorted(events, key=lambda e: e.number):
            self._log_last = event.number
            self.core.handle_event_message(self._log_event_message(event))

    def _log_event_message(self, event: Container) -> Container:
        """The message handle_event_message expects from a live event."""
        date = event.date
        try:
            time_ = datetime.datetime(
                date[0] * 100 + date[1], date[2], date[3], date[4], date[5]
            )
        except ValueError:
            time_ = datetime.datetime.now()
        label = event.label
        element_type = self.event_map.get(event.major, {}).get("type")
        if element_type and "sub" not in self.event_map[event.major]:
            # The log keeps the label from when the event was saved: use today's.
            current = self.core.get_label(element_type, event.minor)
            if current:
                label = current.encode(cfg.LABEL_ENCODING, "replace")
        return Container(
            fields=Container(
                value=Container(
                    po=Container(command=0xE),
                    time=time_,
                    event=Container(major=event.major, minor=event.minor),
                    partition=event.area,
                    module_serial=self.panel_serial.hex() if self.panel_serial else "",
                    label=label,
                )
            )
        )

    def _partition_ready(self, partition: int, zones: dict) -> bool:
        """Ready when no zone of the partition is open.

        Calculated: the panel reports no ready state in any object BabyWare
        reads, nor in its events. Matches the console, which also says "not
        ready" while a motion detector is open.
        """
        return not any(
            self._zone_open(status)
            and self._zone_partitions.get(zone, partition) & partition
            for zone, status in zones.items()
        )

    async def _programming(self, request: bytes) -> bool:
        fragments = await self.transact(SERVICE_PROGRAMMING, request)
        return b"".join(fragments)[PROGRAMMING_STATUS] == bytes(2)

    async def _end_programming(self):
        try:
            if not await self._programming(PROGRAMMING_END):
                logger.warning("MG6250: end of programming session refused")
        except (StatusRequestException, asyncio.TimeoutError) as e:
            logger.warning("MG6250: ending the programming session failed: %s", e)

    async def _write(self, record: bytes, what: str) -> bool:
        """One write inside a programming session, as BabyWare; False if the
        session or the write is refused. A lost reply raises, once the session
        is ended."""
        begun = True  # Begin sent and not refused: End must follow
        try:
            if not await self._programming(PROGRAMMING_BEGIN):
                begun = False
                logger.warning("MG6250: programming session refused")
                return False
            reply = b"".join(await self.transact(SERVICE_OBJECTS, record))
            accepted = reply[WRITE_STATUS] == bytes(2)
            if not accepted:
                logger.warning("MG6250: %s refused, reply %s", what, reply.hex())
            await asyncio.sleep(WRITE_SETTLE)
            return accepted
        finally:
            if begun:
                # Never leave the panel in a programming session, also when
                # the reply to Begin was lost: the panel may have opened it.
                await self._end_programming()

    async def set_time(self, now) -> typing.Optional[bool]:
        """Set the clock as BabyWare: a write inside a programming session.

        The core asks again at every poll while the clock is off, and each try
        opens a programming session: after a refusal there is no other try on
        this connection, after a lost reply none for SET_TIME_RETRY seconds.
        None when no try was made.
        """
        if self._set_time_refused or time.monotonic() < self._set_time_retry_at:
            return None
        accepted = refused = False
        try:
            accepted = await self._write(build_set_time_record(now), "clock write")
            refused = not accepted
        except (StatusRequestException, asyncio.TimeoutError) as e:
            logger.warning("MG6250: setting the clock failed: %s", e)
            self._set_time_retry_at = time.monotonic() + SET_TIME_RETRY
        self._set_time_refused = refused
        return accepted

    async def _not_supported(self, what: str) -> bool:
        logger.warning("MG6250: %s is not supported yet", what)
        return False

    def build_zone_control(self, zone: int, action: int) -> bytes:
        return (
            CONTROL_ZONE_PREFIX
            + self.panel_serial
            + bytes([action, zone])
            + CONTROL_TAIL
        )

    def _control_accepted(self, prefix: bytes, reply: bytes) -> bool:
        serial_end = len(prefix) + len(self.panel_serial)
        return (
            reply[: len(prefix)] == prefix
            and reply[len(prefix) : serial_end] == self.panel_serial
            and reply[serial_end : serial_end + len(CONTROL_OK)] == CONTROL_OK
        )

    async def set_zone_definition(self, zone: int, definition: int) -> bool:
        """Write the definition of a zone, as BabyWare: the whole field 0,
        read again first so that nothing else in it changes."""
        try:
            objects = await self.read_objects(OBJ_ZONE, [zone], (FIELD_SERIAL,))
            field = objects.get(zone, {}).get(FIELD_SERIAL, b"")
            if len(field) <= ZONE_DEFINITION or not field[ZONE_DEFINITION]:
                logger.error("MG6250: zone %d is not enrolled", zone)
                return False
            if field[ZONE_DEFINITION] != definition:
                value = bytearray(field)
                value[ZONE_DEFINITION] = definition
                record = build_write_record(OBJ_ZONE, zone, FIELD_SERIAL, bytes(value))
                if not await self._write(record, f"zone {zone} definition write"):
                    return False
                logger.info(
                    "MG6250: zone %d definition %d -> %d",
                    zone,
                    field[ZONE_DEFINITION],
                    definition,
                )
        except (StatusRequestException, asyncio.TimeoutError) as e:
            logger.exception("MG6250: setting zone %d definition failed: %s", zone, e)
            return False
        if self._zone_definitions.get(zone) != definition:
            self._zone_definitions[zone] = definition
            # publish the new definition
            ps.sendMessage("definitions_loaded", data=await self.load_definitions())
        return True

    async def _set_zone_definitions(self, zones, command: str) -> bool:
        name = command[len(ZONE_DEFINITION_COMMAND) :]
        definition = ZONE_DEFINITION_NUMBERS.get(name)
        if definition is None and name.isdecimal():
            definition = int(name)
        if not definition or definition not in ZONE_DEFINITIONS:
            logger.warning("MG6250: zone command %r is not supported", command)
            return False
        accepted = False
        for zone in zones:
            if await self.set_zone_definition(zone, definition):
                accepted = True
        return accepted

    async def control_zones(self, zones, command) -> bool:
        """Bypass, clear the bypass or set the definition ("definition_instant")
        of zones; True if one was accepted."""
        if command.startswith(ZONE_DEFINITION_COMMAND):
            return await self._set_zone_definitions(zones, command)
        action = ZONE_ACTIONS.get(command)
        if action is None:
            logger.warning("MG6250: zone command %r is not supported", command)
            return False
        if self.panel_serial is None:
            logger.exception("MG6250: panel serial unknown (no identify reply)")
            return False

        accepted = False
        for zone in zones:
            try:
                fragments = await self.transact(
                    SERVICE_CONTROL, self.build_zone_control(zone, action)
                )
            except StatusRequestException as e:
                logger.error("MG6250: %s of zone %d failed: %s", command, zone, e)
                continue
            reply = b"".join(fragments)
            if self._control_accepted(CONTROL_ZONE_PREFIX, reply):
                accepted = True
            else:
                logger.error(
                    "MG6250: %s of zone %d refused, reply %s",
                    command,
                    zone,
                    reply.hex(),
                )
        if accepted:
            self._change_counter = None  # read the status again at the next poll
        return accepted

    def build_control(self, action: int, partition: int = 1) -> bytes:
        return (
            CONTROL_PREFIX
            + self.panel_serial
            + bytes([action, partition])
            + CONTROL_TAIL
        )

    def build_pgm_control(self, pgm: int, action: int) -> bytes:
        return (
            CONTROL_PGM_PREFIX
            + self.panel_serial
            + bytes([action, pgm])
            + CONTROL_PGM_TAIL
        )

    async def control_partitions(self, partitions, command) -> bool:
        """Arm, arm stay, arm sleep or disarm partitions; True if one was
        accepted."""
        action = PARTITION_ACTIONS.get(command)
        if action is None:
            logger.warning("MG6250: partition command %r is not supported", command)
            return False
        if self.panel_serial is None:
            logger.error("MG6250: panel serial unknown (no identify reply)")
            return False

        accepted = False
        for partition in partitions:
            if partition not in self._partitions:
                logger.warning("MG6250: partition %d is not in use", partition)
                continue
            try:
                fragments = await self.transact(
                    SERVICE_CONTROL, self.build_control(action, partition)
                )
            except StatusRequestException as e:
                logger.exception("MG6250: %s failed: %s", command, e)
                continue
            reply = b"".join(fragments)
            expected_reply = CONTROL_PREFIX + self.panel_serial + CONTROL_OK
            if reply.startswith(expected_reply):
                accepted = True
                # A disarm from here does not move the 0x1c change counter
                # (seen live): force the next poll to re-read the status.
                self._change_counter = None
            else:
                logger.error("MG6250: %s refused, reply %s", command, reply.hex())
        return accepted

    async def _control_pgm(self, pgm: int, command: str) -> bool:
        try:
            fragments = await self.transact(
                SERVICE_CONTROL, self.build_pgm_control(pgm, PGM_ACTIONS[command])
            )
        except StatusRequestException as e:
            logger.exception("MG6250: %s of output %d failed: %s", command, pgm, e)
            return False
        reply = b"".join(fragments)
        accepted = self._control_accepted(CONTROL_PGM_PREFIX, reply)
        if not accepted:
            logger.error(
                "MG6250: %s of output %d refused, reply %s", command, pgm, reply.hex()
            )
        return accepted

    async def control_outputs(self, outputs, command) -> bool:
        """on, off, release (BabyWare's Activate, Deactivate, Release) or
        pulse; True if one was accepted. The output state is not read back."""
        if command != PGM_PULSE and command not in PGM_ACTIONS:
            logger.warning("MG6250: output command %r is not supported", command)
            return False
        if self.panel_serial is None:
            logger.error("MG6250: panel serial unknown (no identify reply)")
            return False

        accepted = False
        for pgm in outputs:
            if not 1 <= pgm <= PGM_COUNT:
                logger.warning("MG6250: there is no output %d", pgm)
            elif command != PGM_PULSE:
                accepted |= await self._control_pgm(pgm, command)
            elif await self._control_pgm(pgm, "on"):
                await asyncio.sleep(cfg.OUTPUT_PULSE_DURATION)
                accepted |= await self._control_pgm(pgm, "off")
        return accepted

    async def control_module_pgm_outputs(
        self, module_address, pgm_index, command
    ) -> bool:
        return await self._not_supported("PGM control")

    async def control_doors(self, doors, command) -> bool:
        return await self._not_supported("door control")

    async def dump_memory(self, file, memory_type):
        return await self._not_supported("memory dump")

    async def send_panic(self, partition, panic_type, user_id):
        return await self._not_supported("panic")
