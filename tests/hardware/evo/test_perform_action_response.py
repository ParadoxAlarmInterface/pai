"""
Tests for EVO PerformActionResponse (parse direction, panel -> PAI).

PerformActionResponse layout:
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x4, status nibble)
  1       1     packet_length (PacketLength)
  2       4     _not_used0 (Padding)
  Total fields = 6 bytes + 1 checksum = 7 bytes
  packet_length = 7
"""

# pylint: disable=duplicate-code
from binascii import unhexlify

from paradox.hardware.evo.parsers import PerformActionResponse


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def _build_perform_action_response(
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
):
    """
    Construct PerformActionResponse bytes manually.

    Byte 0: [7:4] command=0x4, [3] reserved, [2] alarm_reporting_pending,
            [1] Winload_connected, [0] NeWare_connected
    Byte 1: packet_length = 7 (6 fields bytes + 1 checksum)
    Bytes 2-5: _not_used0 = 0x00 * 4
    Byte 6: checksum
    """
    b0 = (0x4 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    length = 7
    data = bytes([b0, length, 0x00, 0x00, 0x00, 0x00])
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_perform_action_response_basic():
    """Parse basic PerformActionResponse with no status flags."""
    raw = _build_perform_action_response()
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.command == 0x4
    assert data.fields.value.po.status.reserved is False
    assert data.fields.value.po.status.alarm_reporting_pending is False
    assert data.fields.value.po.status.Winload_connected is False
    assert data.fields.value.po.status.NeWare_connected is False


def test_parse_perform_action_response_winload_connected():
    """Parse PerformActionResponse with Winload connected."""
    raw = _build_perform_action_response(winload_connected=True)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is False


def test_parse_perform_action_response_neware_connected():
    """Parse PerformActionResponse with NeWare connected."""
    raw = _build_perform_action_response(neware_connected=True)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.status.NeWare_connected is True
    assert data.fields.value.po.status.Winload_connected is False


def test_parse_perform_action_response_alarm_reporting_pending():
    """Parse PerformActionResponse with alarm_reporting_pending flag."""
    raw = _build_perform_action_response(alarm_reporting_pending=True)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.status.alarm_reporting_pending is True


def test_parse_perform_action_response_all_flags():
    """Parse PerformActionResponse with all status flags set."""
    raw = _build_perform_action_response(
        reserved=True,
        alarm_reporting_pending=True,
        winload_connected=True,
        neware_connected=True,
    )
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.command == 0x4
    assert data.fields.value.po.status.reserved is True
    assert data.fields.value.po.status.alarm_reporting_pending is True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is True


def test_parse_perform_action_response_known_capture():
    """
    Verify parsing of a known-good capture from test_pgm.py:
    b"42070000000049" — PGM confirmation with 0x4-nibble command.

    Byte 0 = 0x42: command nibble=0x4, status nibble=0x2 → Winload_connected=True
    Byte 1 = 0x07: packet_length=7
    Bytes 2-5 = 0x00...: _not_used0 (padding)
    Byte 6 = 0x49: checksum
    """
    raw = unhexlify("42070000000049")
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.command == 0x4
    # byte 0 = 0x42 → status nibble = 0x2, Winload_connected = True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is False
