"""Construct parsers for Paradox Digiplex panels (DGP-48 / DGP-848 / DGP-NE96).

All frames are 37 bytes: 36 payload bytes + 1 checksum byte
(``sum(payload) % 256``). The field layout below was verified live against a
DGP-848 (firmware build A095, 2026-10) and cross-checked with the frames
published in ParadoxAlarmInterface/pai#257 (avilleret, firmware build A096)
and with tonyrog/digiplex.

Differences from the EVO family:

- The panel answers ONLY to ``StartCommunication`` (0x5F) and only with
  ``source_id=0``; ``InitiateCommunication`` (0x72) is ignored silently.
  This is why upstream PAI cannot talk to Digiplex panels (issue #257).
- Login is done by echoing the StartCommunication response back with the PC
  password (BCD) in bytes [8..9] and a recalculated checksum.
- The panel never broadcasts: status is obtained by polling RAM (READ 0x5x).
"""

from construct import (
    BitsInteger,
    BitStruct,
    Bytes,
    Const,
    Flag,
    Int8ub,
    Int16ub,
    Nibble,
    Padding,
    RawCopy,
    Struct,
)

from ..common import HexInt, PacketChecksum, ProductIdEnum, calculate_checksum

# Re-export the generic StartCommunication (0x5F) request. DGP-848 accepts
# only source_id=0 (NonValid_Source) - any other value is ignored silently.
from ..parsers import StartCommunication  # noqa: F401

# StartCommunication response ("panel passport"). Field offsets differ from
# the EVO family - see the comments for each field.
StartCommunicationResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "address" / Int8ub,  # [1]
            "eeaddr" / Int16ub,  # [2..3]
            "product_id" / ProductIdEnum,  # [4] -> DIGIPLEX_v13 (0) on DGP-848
            "firmware" / Struct("version" / HexInt, "revision" / HexInt),  # [5..6]
            "_not_used0" / Padding(1),  # [7]
            "password_hint" / Bytes(2),  # [8..9] BCD PC password hint
            "_not_used1" / Padding(2),  # [10..11]
            "winload_type_id" / Int8ub,  # [12]
            "memmap_ver" / HexInt,  # [13]
            "event_list_ver" / HexInt,  # [14]
            "firmware_build" / Int16ub,  # [15..16] e.g. 0xA095
            "serial_number" / Bytes(4),  # [17..20]
            "section_data" / Bytes(3),  # [21..23]
            "_not_used2" / Padding(12),  # [24..35]
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

# Login response: [0] = 0x10 on success. On a bad password the panel answers
# with an ErrorMessage (0x70) instead.
InitializeCommunicationResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(1, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "_not_used0" / Padding(35),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

# Error frame: [0] = 0x70, [2] = error code (0x01 = bad PC/user code).
# Also used by the panel as "busy" answer while a PC session is still open.
ErrorMessage = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(7, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "_not_used0" / Padding(1),
            "message" / Int8ub,  # [2] error code
            "_not_used1" / Padding(33),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

# READ (0x5x): count is a 5 bit value split over two fields
# (count = count_hi << 1 | count_lo, 32 is encoded as 0).
# address | 0x8000 = RAM, address & 0x7FFF = EEPROM.
ReadRAM = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / BitStruct("command" / Const(5, Nibble), "count_hi" / BitsInteger(4)),
            "bus" / BitStruct("count_lo" / Flag, "bus_address" / BitsInteger(7)),
            "address" / Int16ub,
            "_not_used0" / Padding(32),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

ReadRAMResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / BitStruct("command" / Const(5, Nibble), "count_hi" / BitsInteger(4)),
            "bus" / BitStruct("count_lo" / Flag, "bus_address" / BitsInteger(7)),
            "address" / Int16ub,
            "data" / Bytes(32),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)


# EVENT (0xE): the panel either broadcasts these on its own (byte[1] == 0xFF)
# or answers an event-log request. The Digiplex layout per tonyrog/digiplex:
#
#   [1]      event request number (0xFF = live/broadcast event)
#   [2..7]   century, year, month, day, hour, minute
#   [8]      event group
#   [9]      partition nibbles (P1 high nibble, P2 low nibble)
#   [10]     event number 1
#   [11]     event number 2
#   [12..15] module serial
#   [16..35] event data (text)
#
# brendankmurphy's DGP-NE96 bridge uses bytes [10] (event) and [12]
# (sub-event) instead, so the exact offsets still have to be confirmed from a
# live capture. Until then we only keep the raw payload and log it - no
# interpretation, no risk of publishing wrong events.
EventResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xE, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "raw" / Bytes(34),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)


# MONITOR (0x40): partition commands. One nibble per partition, packed two per
# byte after a 0x00 pad:
#
#   40 00 | P1:P2 | P3:P4 | P5:P6 | P7:P8
#
# Command values (tonyrog/digiplex, cross-checked with
# adumat/paradox-dgp-mqtt): NOP=0x0, FULL_ARM=0x2, STAY_ARM=0x3,
# INSTANT_ARM=0x4, FORCE_ARM=0x5, DISARM=0x6, BEEP=0x8.
#
# No user code is sent: authority comes from the PC session (verified with the
# other Digiplex implementations). The panel answers with an echo of the same
# frame (command nibble 0x4) or an ErrorMessage (0x70).
PARTITION_ACTION_COMMANDS = {
    "arm": 0x2,  # full arm        -> armed_away
    "arm_stay": 0x3,  # stay arm   -> panel reports the stay bit -> armed_home
    # HA's "night" maps to the same stay arm: this panel reports INSTANT_ARM
    # (0x4) as a full arm (no stay bit), which would show up as armed_away and
    # confuse the night mode. Instant arm is therefore not exposed.
    "arm_sleep": 0x3,
    "force": 0x5,
    "disarm": 0x6,
    "beep": 0x8,
}

PerformPartitionAction = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0x4, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "_not_used0" / Padding(1),
            "partitions" / Bytes(4),  # four packed nibble pairs
            "_not_used1" / Padding(30),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)


def build_partition_action(partitions: dict) -> bytes:
    """Build a MONITOR frame from ``{partition_number: command_nibble}``."""
    nibbles = [0] * 8
    for number, command in partitions.items():
        number = int(number)
        if 1 <= number <= 8:
            nibbles[number - 1] = command & 0x0F

    packed = bytes(
        (
            (nibbles[0] << 4) | nibbles[1],
            (nibbles[2] << 4) | nibbles[3],
            (nibbles[4] << 4) | nibbles[5],
            (nibbles[6] << 4) | nibbles[7],
        )
    )
    payload = bytes((0x40, 0x00)) + packed + bytes(30)
    return payload + calculate_checksum(payload)


def build_read_ram(address: int, count: int = 32, bus_address: int = 0) -> bytes:
    """Build a READ frame (count 1..32, 32 is encoded as 0)."""
    if not (1 <= count <= 32):
        raise ValueError("count must be 1..32")
    c = count % 32
    return ReadRAM.build(
        dict(
            fields=dict(
                value=dict(
                    po=dict(count_hi=c >> 1),
                    bus=dict(count_lo=bool(c & 1), bus_address=bus_address),
                    address=address,
                )
            )
        )
    )


def build_login(init_response_raw: bytes, password: bytes) -> bytes:
    """Build the LOGIN frame: echo of the init response with the PC password
    (BCD, 2 bytes) in [8..9] and a recalculated checksum."""
    login = bytearray(init_response_raw[:36])
    login[8] = password[0]
    login[9] = password[1]
    return bytes(login) + calculate_checksum(bytes(login))
