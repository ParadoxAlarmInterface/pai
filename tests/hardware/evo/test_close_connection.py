"""
Tests for EVO CloseConnection (build direction, PAI -> panel).

CloseConnection layout:
  Offset  Size  Field
  0       1     po.command = 0x70
  1       1     length (PacketLength = fields.sizeof() + 1)
  2       1     message (Enum, default 0x05 = panel_will_disconnect)
  Total fields = 3 bytes + 1 byte checksum = 4 bytes
"""

from binascii import unhexlify

from paradox.hardware.evo.parsers import CloseConnection


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def test_build_close_connection_default_message():
    """Build with default message (panel_will_disconnect = 0x05)."""
    raw = CloseConnection.build({"fields": {"value": {}}})

    # Byte 0: command = 0x70
    assert raw[0] == 0x70
    # Byte 1: length = 4 (3 fields bytes + 1 checksum byte)
    assert raw[1] == 4
    # Byte 2: default message = 0x05 (panel_will_disconnect)
    assert raw[2] == 0x05
    # Total length
    assert len(raw) == 4
    # Checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_invalid_user_code():
    """Build with message = invalid_user_code (0x01)."""
    raw = CloseConnection.build({"fields": {"value": {"message": "invalid_user_code"}}})

    assert raw[0] == 0x70
    assert raw[2] == 0x01
    assert len(raw) == 4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_invalid_pc_password():
    """Build with message = invalid_pc_password (0x12)."""
    raw = CloseConnection.build(
        {"fields": {"value": {"message": "invalid_pc_password"}}}
    )

    assert raw[0] == 0x70
    assert raw[2] == 0x12
    assert len(raw) == 4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_panel_not_connected():
    """Build with message = panel_not_connected (0x10)."""
    raw = CloseConnection.build(
        {"fields": {"value": {"message": "panel_not_connected"}}}
    )

    assert raw[0] == 0x70
    assert raw[2] == 0x10
    assert len(raw) == 4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_panel_already_connected():
    """Build with message = panel_already_connected (0x11)."""
    raw = CloseConnection.build(
        {"fields": {"value": {"message": "panel_already_connected"}}}
    )

    assert raw[0] == 0x70
    assert raw[2] == 0x11
    assert len(raw) == 4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_known_hex():
    """
    Build default CloseConnection and verify against known hex.
    Expected: 0x70, length=0x04, message=0x05, checksum = (0x70+0x04+0x05)%256 = 0x79
    """
    raw = CloseConnection.build({"fields": {"value": {}}})
    expected = unhexlify("70040579")
    assert raw == expected
