"""Paradox MG6250 panel support (encrypted link)

Login, labels (zones, keypads, repeaters, sirens, users, partition 1), the
panel clock, battery and AC voltage, zone open/alarm and partition 1 exit
delay/armed/alarm as status (the alarm bits are provisional), and arm / arm
stay / arm sleep / disarm of partition 1. Stay/sleep status and other
controls, including time synchronization, are not implemented.
"""

import asyncio
import datetime
import logging
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
from paradox.lib.crypto import decrypt as paradox_decrypt, encrypt as paradox_encrypt
from paradox.lib.handlers import Handler

from ..panel import Panel as PanelBase

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

LOGIN_STATUS = {
    0x00: "accepted",
    0x05: "busy (previous session still open)",
    0x81: "rejected: unknown session id",
    0x83: "rejected: unknown user",
    0x84: "rejected: bad PW_BLOCK credential",
    0x85: "busy (previous session still open)",
}

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
LAST_FRAGMENT = 0x8000
# The panel drops a request sent right after our last ack (live test: every
# such request needed a retry). BabyWare waits at least 60 ms.
ACK_GAP = 0.1

SERVICE_OBJECTS = 0x17  # read/write configuration objects
SERVICE_CONTROL = 0x18  # actions: arm, disarm
OP_READ = 0x00

# Service 0x18 request: CONTROL_PREFIX | panel serial | action | CONTROL_TARGET.
# The reply echoes prefix and serial, then 3 status bytes (00 00 00 = done).
# One capture per action (arm-sleep-09, arm-full-09, stay).
PARTITION_ACTIONS = {"disarm": 0x10, "arm_stay": 0x11, "arm_sleep": 0x12, "arm": 0x13}
CONTROL_PREFIX = b"\x00\xff" + bytes(5)
# The same in every capture, all on partition 1; which byte is the
# partition is not known, so only partition 1 can be controlled.
CONTROL_TARGET = bytes.fromhex("010001000000")
CONTROL_OK = bytes(3)
CONTROL_PARTITIONS = [1]
IDENTIFY_SERIAL = slice(8, 12)  # panel serial in the first identify reply

# Objects (big-endian ids), with the index count BabyWare reads
OBJ_ZONE = 0x0001
OBJ_KEYPAD = 0x0009
OBJ_REPEATER = 0x000B
OBJ_SIREN = 0x000D
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
CLOCK_FIELDS = (0, 1, 2, 3)  # BabyWare's selection; field 1 is the date
CLOCK_FIELD_DATE = 1  # century, year, month, day, hour, minute
# battery | AC | unknown, one byte each. BabyWare showed Battery 5.3 V and AC
# 0.0 for 42 00 0c: 0.08 V per step (20.4 V full scale) fits, but rests on
# that one reading.
CLOCK_FIELD_POWER = 2
VOLTS_PER_STEP = 0.08
SYSTEM_FIELDS = (0, 1)  # what BabyWare polls every 20 s
SYSTEM_FIELD_STATUS = 1  # byte 0: counter, changes when a zone does
# byte 0: non-zero = open (01; 04 on the zone in alarm); byte 1: flags below;
# byte 2 unknown
ZONE_STATUS_FIELD = 0
# Provisional, from one alarm capture (and set-sms for the memory flag).
# Zone status byte 1: 0x04 on every zone during the exit delay (not used),
# 0x10 on the zone in alarm, 0x20 alarm in memory (stays once closed).
ZONE_IN_ALARM = 0x10
ZONE_ALARM_MEMORY = 0x20
# Partition status field 0: state | flags | flags | 3 unknown. Seen:
# disarmed 00 00 00, exit delay 03 00 01, armed 07 00 00, alarm 77 02 40.
# Stay and sleep have not been captured: they show as armed.
PARTITION_STATUS_FIELD = 0
PARTITION_ARMED = 0x04  # state byte, once the exit delay is over
PARTITION_ALARM = 0x70  # state byte, all three set in the one alarm seen
PARTITION_EXIT_DELAY = 0x01  # third byte

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
    """Consumes the panel's acks of our requests; transact waits for the data."""

    NAME = "MG6250 panel ack"

    def __init__(self, panel):
        super().__init__(name=self.NAME)
        self.panel = panel

    def can_handle(self, data) -> bool:
        return self.panel.is_panel_ack(data)

    async def __call__(self, data):
        pass


class Panel(PanelBase):
    event_map = {}  # TODO
    property_map = {}  # TODO
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

    def is_panel_ack(self, message) -> bool:
        decrypted = self._decrypt_message(message)
        return decrypted is not None and decrypted[0].kind == KIND_ACK

    async def transact(self, service: int, data: bytes) -> typing.List[bytes]:
        """Send one request, ACK each reply fragment, return their data.

        Each fragment is padded on its own, so parse them separately.
        """
        if self._transaction_lock is None:
            self._transaction_lock = asyncio.Lock()
        async with self._transaction_lock:
            self._tid = self._tid % 0xFF + 1
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
        registry = self.core.connection.handler_registry
        registry.remove_by_name(PanelAckHandler.NAME)  # after a re-login
        registry.append(PanelAckHandler(self))
        logger.info(
            "MG6250 session: selector 0x%02x mode 0x%02x user %r",
            self.session.selector,
            self.session.mode,
            self.session.label.decode("ascii", "replace").rstrip(),
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
    async def load_labels(self):
        data = {}
        for elem_type, (obj, count) in LABEL_OBJECTS.items():
            start_time = time.time()
            indexes = get_limits_for_type(elem_type, list(range(1, count + 1)))
            objects = await self.read_objects(obj, indexes, (FIELD_SERIAL, FIELD_LABEL))
            elements = data[elem_type] = {}
            for index in sorted(indexes):
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
                elements[index] = element
            self.log_labels_loaded(elem_type, elements, start_time)
        self._zones = sorted(data["zone"])

        # Users have no serial: list them all, as for the other panels.
        start_time = time.time()
        indexes = get_limits_for_type("user", list(range(1, USER_COUNT + 1)))
        users = await self.read_objects(OBJ_USER, indexes, (FIELD_LABEL,))
        data["user"] = {
            index: self.label_element(
                "user", index, self.decode_label(fields.get(FIELD_LABEL, b""))
            )
            for index, fields in sorted(users.items())
        }
        self.log_labels_loaded("user", data["user"], start_time)

        # Only the partition that can be controlled is listed.
        start_time = time.time()
        indexes = [
            i
            for i in get_limits_for_type("partition", CONTROL_PARTITIONS)
            if i in CONTROL_PARTITIONS
        ]
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
                    for i in CONTROL_PARTITIONS
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
                for index in CONTROL_PARTITIONS
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
                ac=round(power[1] * VOLTS_PER_STEP, 1),
            )
        zones = self._zone_status
        partitions = self._partition_status
        return Container(
            system=system,
            zone_open={i: v[0] != 0 for i, v in zones.items()},
            zone_presently_in_alarm={
                i: bool(v[1] & ZONE_IN_ALARM) for i, v in zones.items()
            },
            zone_generated_alarm={
                i: bool(v[1] & ZONE_ALARM_MEMORY) for i, v in zones.items()
            },
            partition_arm={
                i: bool(v[0] & PARTITION_ARMED) for i, v in partitions.items()
            },
            partition_exit_delay={
                i: bool(v[2] & PARTITION_EXIT_DELAY) for i, v in partitions.items()
            },
            partition_audible_alarm={
                i: bool(v[0] & PARTITION_ALARM) for i, v in partitions.items()
            },
        )

    async def _not_supported(self, what: str) -> bool:
        logger.warning("MG6250: %s is not supported yet", what)
        return False

    async def control_zones(self, zones, command) -> bool:
        return await self._not_supported("zone control")

    def build_control(self, action: int) -> bytes:
        return CONTROL_PREFIX + self.panel_serial + bytes([action]) + CONTROL_TARGET

    async def control_partitions(self, partitions, command) -> bool:
        """Arm, arm stay, arm sleep or disarm partition 1; True if accepted."""
        action = PARTITION_ACTIONS.get(command)
        if action is None:
            logger.warning("MG6250: partition command %r is not supported", command)
            return False
        if self.panel_serial is None:
            logger.error("MG6250: panel serial unknown (no identify reply)")
            return False

        accepted = False
        for partition in partitions:
            if partition not in CONTROL_PARTITIONS:
                logger.warning("MG6250: only partition 1 can be controlled")
                continue
            try:
                fragments = await self.transact(
                    SERVICE_CONTROL, self.build_control(action)
                )
            except StatusRequestException:
                logger.exception("MG6250: %s failed", command)
                continue
            reply = b"".join(fragments)
            expected_reply = CONTROL_PREFIX + self.panel_serial + CONTROL_OK
            if reply.startswith(expected_reply):
                accepted = True
            else:
                logger.error("MG6250: %s refused, reply %s", command, reply.hex())
        return accepted

    async def control_outputs(self, outputs, command) -> bool:
        return await self._not_supported("output control")

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
