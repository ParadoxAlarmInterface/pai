"""
Tests for Spectra/Magellan CloseConnection (build direction, PAI -> panel).

CloseConnection layout:
  Offset  Size  Field
  0       1     po.command = 0x70
  1       1     _not_used0 = 0x00 (Const)
  2       1     validation_byte (default 0)
  3       29    _not_used1 (Padding)
  32      1     message (Enum, default 0x05 = panel_will_disconnect)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

from paradox.hardware.spectra_magellan.parsers import CloseConnection


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def test_build_close_connection_defaults():
    """Build CloseConnection with defaults."""
    raw = CloseConnection.build({"fields": {"value": {}}})

    # command = 0x70
    assert raw[0] == 0x70
    # _not_used0 = 0x00 (Const)
    assert raw[1] == 0x00
    # validation_byte = 0 (default)
    assert raw[2] == 0x00
    # Total length = 37 bytes
    assert len(raw) == 37
    # message (panel_will_disconnect = 0x05) at offset 32
    assert raw[32] == 0x05
    # source_id (Winload_Direct = 1) at offset 33
    assert raw[33] == 0x01
    # user_id = 0 at offsets 34-35 (little-endian)
    assert raw[34] == 0x00
    assert raw[35] == 0x00
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_authentication_failed():
    """Build CloseConnection with authentication_failed message."""
    raw = CloseConnection.build(
        {"fields": {"value": {"message": "authentication_failed"}}}
    )

    assert raw[32] == 0x12
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_panel_will_disconnect():
    """Build CloseConnection with explicit panel_will_disconnect message."""
    raw = CloseConnection.build(
        {"fields": {"value": {"message": "panel_will_disconnect"}}}
    )

    assert raw[32] == 0x05
    assert raw[-1] == _checksum(raw[:-1])


def test_build_close_connection_total_length():
    """Total packet must be 37 bytes."""
    raw = CloseConnection.build({"fields": {"value": {}}})
    assert len(raw) == 37


def test_build_close_connection_checksum_validity():
    """Checksum must be sum of all preceding bytes mod 256."""
    raw = CloseConnection.build({"fields": {"value": {}}})
    assert raw[-1] == _checksum(raw[:-1])
