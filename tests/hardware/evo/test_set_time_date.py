"""
Tests for EVO SetTimeDate (build) and SetTimeDateResponse (parse).

SetTimeDate layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x30
  1       1     packet_length (PacketLength)
  2       4     _not_used0 (Padding)
  6       1     century
  7       1     year
  8       1     month
  9       1     day
  10      1     hour
  11      1     minute
  Total fields = 12 bytes + 1 checksum = 13 bytes
  packet_length = 13

SetTimeDateResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x3, status nibble)
  1       1     length
  2       4     _not_used0 (Padding)
  Total fields = 6 bytes + 1 checksum = 7 bytes
"""

# pylint: disable=duplicate-code
from paradox.hardware.evo.parsers import SetTimeDate, SetTimeDateResponse


def _checksum(data: bytes) -> int:
    return sum(data) % 256


# ---------------------------------------------------------------------------
# SetTimeDate — BUILD tests
# ---------------------------------------------------------------------------


def test_build_set_time_date_basic():
    """Build SetTimeDate with a known date/time."""
    raw = SetTimeDate.build(
        {
            "fields": {
                "value": {
                    "century": 20,
                    "year": 26,
                    "month": 2,
                    "day": 19,
                    "hour": 10,
                    "minute": 30,
                }
            }
        }
    )

    # command = 0x30 at byte 0
    assert raw[0] == 0x30
    # packet_length at byte 1
    assert raw[1] == len(raw)
    # padding at bytes 2-5 = 0x00
    assert raw[2:6] == b"\x00\x00\x00\x00"
    # century at byte 6
    assert raw[6] == 20
    # year at byte 7
    assert raw[7] == 26
    # month at byte 8
    assert raw[8] == 2
    # day at byte 9
    assert raw[9] == 19
    # hour at byte 10
    assert raw[10] == 10
    # minute at byte 11
    assert raw[11] == 30
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_set_time_date_total_length():
    """Total packet length = 13 bytes (12 fields + 1 checksum)."""
    raw = SetTimeDate.build(
        {
            "fields": {
                "value": {
                    "century": 20,
                    "year": 24,
                    "month": 1,
                    "day": 1,
                    "hour": 0,
                    "minute": 0,
                }
            }
        }
    )
    assert len(raw) == 13


def test_build_set_time_date_checksum_validity():
    """Checksum must be sum of all preceding bytes mod 256."""
    raw = SetTimeDate.build(
        {
            "fields": {
                "value": {
                    "century": 19,
                    "year": 99,
                    "month": 12,
                    "day": 31,
                    "hour": 23,
                    "minute": 59,
                }
            }
        }
    )
    assert raw[-1] == _checksum(raw[:-1])


def test_build_set_time_date_midnight():
    """Build for midnight to verify zero time fields work correctly."""
    raw = SetTimeDate.build(
        {
            "fields": {
                "value": {
                    "century": 20,
                    "year": 0,
                    "month": 1,
                    "day": 1,
                    "hour": 0,
                    "minute": 0,
                }
            }
        }
    )
    assert raw[10] == 0  # hour
    assert raw[11] == 0  # minute
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# SetTimeDateResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_set_time_date_response(
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
):
    """
    Construct SetTimeDateResponse bytes manually.

    Byte 0: [7:4] command=0x3, [3] reserved, [2] alarm_reporting_pending,
            [1] Winload_connected, [0] NeWare_connected
    Byte 1: length = 7 (6 fields + 1 checksum)
    Bytes 2-5: _not_used0 = 0x00 * 4
    Byte 6: checksum
    """
    b0 = (0x3 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    length = 7  # 6 fields + 1 checksum
    data = bytes([b0, length, 0x00, 0x00, 0x00, 0x00])
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_set_time_date_response_basic():
    """Parse basic SetTimeDateResponse with no flags set."""
    raw = _build_set_time_date_response()
    data = SetTimeDateResponse.parse(raw)

    assert data.fields.value.po.command == 0x3
    assert data.fields.value.po.status.reserved is False
    assert data.fields.value.po.status.alarm_reporting_pending is False
    assert data.fields.value.po.status.Winload_connected is False
    assert data.fields.value.po.status.NeWare_connected is False


def test_parse_set_time_date_response_winload_connected():
    """Parse SetTimeDateResponse with Winload connected."""
    raw = _build_set_time_date_response(winload_connected=True)
    data = SetTimeDateResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is False


def test_parse_set_time_date_response_all_flags():
    """Parse SetTimeDateResponse with all status flags set."""
    raw = _build_set_time_date_response(
        reserved=True,
        alarm_reporting_pending=True,
        winload_connected=True,
        neware_connected=True,
    )
    data = SetTimeDateResponse.parse(raw)

    assert data.fields.value.po.status.reserved is True
    assert data.fields.value.po.status.alarm_reporting_pending is True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is True
