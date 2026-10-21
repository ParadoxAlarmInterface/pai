"""
Tests for EVO BroadcastRequest (build), BroadcastResponse (parse),
and PGMBroadcastCommand (build).

BroadcastRequest layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po (BitStruct: command=0xA nibble, module_type Flag, sub_command BitsInteger(3))
  1       1     packet_length (PacketLength = fields.sizeof() + 1)
  2       1     bus_address (default 0x00)
  3       3     _not_used (Padding)
  6       16    data (Bytes(16))
  Total fields = 22 bytes + 1 checksum = 23 bytes

BroadcastResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command=0xA nibble, status 4 flags)
  1       1     packet_length
  2       1     bus_address
  3       1     control (BitStruct: ram_access, _not_used[5], _eeprom_address_bits[2])
  4       2     address (Int16ub, lower 16 bits; adapter adds upper bits from control)
  Total fields = 6 bytes + 1 checksum = 7 bytes

PGMBroadcastCommand: DictArray(16, 1, ...) with Enum(Int8ub) command per PGM
  16 bytes total (one byte per PGM output, indices 1-16)
"""

from paradox.hardware.evo.parsers import (
    BroadcastRequest,
    BroadcastResponse,
    PGMBroadcastCommand,
)


def _checksum(data: bytes) -> int:
    return sum(data) % 256


# ---------------------------------------------------------------------------
# BroadcastRequest — BUILD tests
# ---------------------------------------------------------------------------


def test_build_broadcast_request_general_broadcast():
    """Build BroadcastRequest with general_broadcast sub_command and zero data."""
    data_payload = b"\x00" * 16
    raw = BroadcastRequest.build(
        {
            "fields": {
                "value": {
                    "po": {"sub_command": "general_broadcast"},
                    "data": data_payload,
                }
            }
        }
    )

    # Total length = 23 bytes
    assert len(raw) == 23
    # Byte 0: command nibble 0xA at bits [7:4], module_type=False, sub_command=0
    # = 0xA0 (general_broadcast=0, module_type=False)
    assert raw[0] == 0xA0
    # packet_length = 23 at byte 1
    assert raw[1] == 23
    # bus_address = 0x00 at byte 2
    assert raw[2] == 0x00
    # padding bytes 3-5 = 0x00
    assert raw[3:6] == b"\x00\x00\x00"
    # data bytes 6-21 = 0x00
    assert raw[6:22] == data_payload
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_broadcast_request_pgm_override():
    """Build BroadcastRequest with pgm_override sub_command."""
    data_payload = b"\x01" + b"\x00" * 15
    raw = BroadcastRequest.build(
        {
            "fields": {
                "value": {
                    "po": {"sub_command": "pgm_override"},
                    "data": data_payload,
                }
            }
        }
    )

    assert len(raw) == 23
    # sub_command = 4 (pgm_override) in bits [2:0] of byte 0
    # module_type=False (bit 3), sub_command=4 (bits 2-0)
    # po byte = 0xA << 4 | 0 << 3 | 4 = 0xA4
    assert raw[0] == 0xA4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_broadcast_request_lcd_message():
    """Build BroadcastRequest with lcd_message_high_prority sub_command."""
    data_payload = b"Hello World!    "  # 16 bytes
    raw = BroadcastRequest.build(
        {
            "fields": {
                "value": {
                    "po": {"sub_command": "lcd_message_high_prority"},
                    "data": data_payload,
                }
            }
        }
    )

    assert len(raw) == 23
    # sub_command = 3 (lcd_message_high_prority)
    # po byte = 0xA3
    assert raw[0] == 0xA3
    # data should be at bytes 6-21
    assert raw[6:22] == data_payload
    assert raw[-1] == _checksum(raw[:-1])


def test_build_broadcast_request_with_bus_address():
    """Build BroadcastRequest targeting a specific bus address."""
    data_payload = b"\x00" * 16
    raw = BroadcastRequest.build(
        {
            "fields": {
                "value": {
                    "po": {"sub_command": "general_broadcast"},
                    "bus_address": 0x01,
                    "data": data_payload,
                }
            }
        }
    )

    assert raw[2] == 0x01
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# BroadcastResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_broadcast_response_bytes(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
    bus_address=0x00,
    ram_access=False,
    eeprom_address_bits=0,
    address=0x0000,
):
    """
    Manually construct BroadcastResponse bytes.

    Byte 0: [7:4]=0xA (command), [3]=reserved, [2]=alarm_reporting_pending,
            [1]=Winload_connected, [0]=NeWare_connected
    Byte 1: packet_length = 7 (6 fields + 1 checksum)
    Byte 2: bus_address
    Byte 3: control = [7]=ram_access, [6:2]=0, [1:0]=eeprom_address_bits
    Bytes 4-5: address big-endian (lower 16 bits)
    Byte 6: checksum
    """
    b0 = (0xA << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    length = 7
    b3 = (int(ram_access) << 7) | (eeprom_address_bits & 0x3)
    b4 = (address >> 8) & 0xFF
    b5 = address & 0xFF
    data = bytes([b0, length, bus_address, b3, b4, b5])
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_broadcast_response_basic():
    """Parse basic BroadcastResponse with no flags, address=0."""
    raw = _build_broadcast_response_bytes()
    data = BroadcastResponse.parse(raw)

    assert data.fields.value.po.command == 0xA
    assert data.fields.value.po.status.reserved is False
    assert data.fields.value.po.status.Winload_connected is False
    assert data.fields.value.po.status.NeWare_connected is False
    assert data.fields.value.bus_address == 0x00
    assert data.fields.value.address == 0x0000


def test_parse_broadcast_response_with_address():
    """Parse BroadcastResponse with a non-zero address."""
    raw = _build_broadcast_response_bytes(address=0x1000)
    data = BroadcastResponse.parse(raw)

    assert data.fields.value.address == 0x1000


def test_parse_broadcast_response_winload_connected():
    """Parse BroadcastResponse with Winload connected status."""
    raw = _build_broadcast_response_bytes(winload_connected=True)
    data = BroadcastResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True


def test_parse_broadcast_response_with_bus_address():
    """Parse BroadcastResponse targeting a module bus address."""
    raw = _build_broadcast_response_bytes(bus_address=0x05)
    data = BroadcastResponse.parse(raw)

    assert data.fields.value.bus_address == 0x05


# ---------------------------------------------------------------------------
# PGMBroadcastCommand — BUILD tests
# ---------------------------------------------------------------------------


def test_build_pgm_broadcast_command_all_no_change():
    """Build PGMBroadcastCommand with all PGMs set to no_change."""
    raw = PGMBroadcastCommand.build({i: "no_change" for i in range(1, 17)})

    # 16 bytes, all 0x00 (no_change = 0)
    assert len(raw) == 16
    assert raw == b"\x00" * 16


def test_build_pgm_broadcast_command_pgm1_override_on():
    """Build PGMBroadcastCommand with PGM 1 set to override_on."""
    commands = {i: "no_change" for i in range(1, 17)}
    commands[1] = "override_on"

    raw = PGMBroadcastCommand.build(commands)

    assert len(raw) == 16
    # PGM 1 override_on = 2
    assert raw[0] == 2
    # All others = 0
    assert raw[1:] == b"\x00" * 15


def test_build_pgm_broadcast_command_pgm8_override_off():
    """Build PGMBroadcastCommand with PGM 8 set to override_off."""
    commands = {i: "no_change" for i in range(1, 17)}
    commands[8] = "override_off"

    raw = PGMBroadcastCommand.build(commands)

    assert len(raw) == 16
    # PGM 8 override_off = 1
    assert raw[7] == 1
    # All others = 0
    assert all(b == 0 for i, b in enumerate(raw) if i != 7)


def test_build_pgm_broadcast_command_pgm16_release():
    """Build PGMBroadcastCommand with PGM 16 set to release."""
    commands = {i: "no_change" for i in range(1, 17)}
    commands[16] = "release"

    raw = PGMBroadcastCommand.build(commands)

    assert len(raw) == 16
    # PGM 16 release = 4
    assert raw[15] == 4


def test_build_pgm_broadcast_command_mixed():
    """Build PGMBroadcastCommand with mixed commands."""
    commands = {i: "no_change" for i in range(1, 17)}
    commands[1] = "override_on"  # = 2
    commands[2] = "override_off"  # = 1
    commands[3] = "release_off"  # = 3
    commands[4] = "release"  # = 4

    raw = PGMBroadcastCommand.build(commands)

    assert len(raw) == 16
    assert raw[0] == 2  # PGM 1: override_on
    assert raw[1] == 1  # PGM 2: override_off
    assert raw[2] == 3  # PGM 3: release_off
    assert raw[3] == 4  # PGM 4: release
    assert all(raw[i] == 0 for i in range(4, 16))
