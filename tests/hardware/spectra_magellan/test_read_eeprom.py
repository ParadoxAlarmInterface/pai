"""
Tests for Spectra/Magellan ReadEEPROM (build) and ReadStatusResponse (parse).

ReadEEPROM layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x50
  1       1     _not_used0 (Padding)
  2       2     address (Int16ub, default 0)
  4       29    _not_used1 (Padding)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  Total fields = 36 bytes + 1 checksum = 37 bytes

ReadStatusResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x5, status nibble)
  1       1     _not_used0 (Padding)
  2       1     validation = 0x80 (Const)
  3       1     address (Int8ub, RAM block index)
  4       32    data (Bytes(32))
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

import pytest

from paradox.hardware.spectra_magellan.parsers import ReadEEPROM, ReadStatusResponse


def _checksum(data: bytes) -> int:
    return sum(data) % 256


# ---------------------------------------------------------------------------
# ReadEEPROM — BUILD tests
# ---------------------------------------------------------------------------


def test_build_read_eeprom_defaults():
    """Build ReadEEPROM with default values."""
    raw = ReadEEPROM.build({"fields": {"value": {}}})

    # command = 0x50 at byte 0
    assert raw[0] == 0x50
    # Total length = 37 bytes
    assert len(raw) == 37
    # address = 0x0000 at bytes 2-3
    assert raw[2] == 0x00
    assert raw[3] == 0x00
    # source_id (Winload_Direct = 1) at byte 33
    assert raw[33] == 0x01
    # user_id = 0 at bytes 34-35 (little-endian)
    assert raw[34] == 0x00
    assert raw[35] == 0x00
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_read_eeprom_address_zero():
    """Build ReadEEPROM targeting EEPROM address 0."""
    raw = ReadEEPROM.build({"fields": {"value": {"address": 0x0000}}})

    assert raw[2] == 0x00
    assert raw[3] == 0x00
    assert raw[-1] == _checksum(raw[:-1])


def test_build_read_eeprom_address_nonzero():
    """Build ReadEEPROM targeting a non-zero EEPROM address."""
    raw = ReadEEPROM.build({"fields": {"value": {"address": 0x0100}}})

    # address big-endian at bytes 2-3
    assert raw[2] == 0x01
    assert raw[3] == 0x00
    assert raw[-1] == _checksum(raw[:-1])


def test_build_read_eeprom_address_max():
    """Build ReadEEPROM with maximum 16-bit address."""
    raw = ReadEEPROM.build({"fields": {"value": {"address": 0xFFFF}}})

    assert raw[2] == 0xFF
    assert raw[3] == 0xFF
    assert raw[-1] == _checksum(raw[:-1])


def test_build_read_eeprom_total_length():
    """Total packet must be 37 bytes."""
    raw = ReadEEPROM.build({"fields": {"value": {}}})
    assert len(raw) == 37


@pytest.mark.parametrize("address", [0x0000, 0x0001, 0x0020, 0x0080, 0x0100, 0x8000])
def test_build_read_eeprom_various_addresses(address):
    """Various EEPROM addresses build correctly with valid checksums."""
    raw = ReadEEPROM.build({"fields": {"value": {"address": address}}})
    assert raw[2] == (address >> 8) & 0xFF
    assert raw[3] == address & 0xFF
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# ReadStatusResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_read_status_response(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
    address=0x00,
    data_payload=None,
):
    """
    Construct ReadStatusResponse bytes manually.

    Byte 0: [7:4]=0x5 (command), [3]=reserved, [2]=alarm_reporting_pending,
            [1]=Winload_connected, [0]=NeWare_connected
    Byte 1: _not_used0 = 0x00
    Byte 2: validation = 0x80
    Byte 3: address (RAM block index)
    Bytes 4-35: data (32 bytes)
    Byte 36: checksum
    """
    if data_payload is None:
        data_payload = b"\x00" * 32
    assert len(data_payload) == 32

    b0 = (0x5 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    raw_data = bytes([b0, 0x00, 0x80, address]) + data_payload
    cs = _checksum(raw_data)
    return raw_data + bytes([cs])


def test_parse_read_status_response_basic():
    """Parse basic ReadStatusResponse with all-zero data."""
    raw = _build_read_status_response()
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.po.command == 0x5
    assert data.fields.value.po.status.reserved is False
    assert data.fields.value.po.status.Winload_connected is False
    assert data.fields.value.po.status.NeWare_connected is False
    assert data.fields.value.address == 0
    assert data.fields.value.data == b"\x00" * 32


def test_parse_read_status_response_address_1():
    """Parse ReadStatusResponse for RAM block address 1."""
    raw = _build_read_status_response(address=1)
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.address == 1


def test_parse_read_status_response_address_2():
    """Parse ReadStatusResponse for RAM block address 2."""
    raw = _build_read_status_response(address=2)
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.address == 2


def test_parse_read_status_response_with_data():
    """Parse ReadStatusResponse with meaningful data payload."""
    payload = bytes(range(32))
    raw = _build_read_status_response(data_payload=payload)
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.data == payload


def test_parse_read_status_response_winload_connected():
    """Parse ReadStatusResponse with Winload connected."""
    raw = _build_read_status_response(winload_connected=True, address=0)
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True


def test_parse_read_status_response_all_status_flags():
    """Parse ReadStatusResponse with all status flags set."""
    raw = _build_read_status_response(
        reserved=True,
        alarm_reporting_pending=True,
        winload_connected=True,
        neware_connected=True,
    )
    data = ReadStatusResponse.parse(raw)

    assert data.fields.value.po.status.reserved is True
    assert data.fields.value.po.status.alarm_reporting_pending is True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is True
