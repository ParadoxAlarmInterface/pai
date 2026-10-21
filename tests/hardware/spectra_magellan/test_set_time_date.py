"""
Tests for Spectra/Magellan SetTimeDate (build) and SetTimeDateResponse (parse).

SetTimeDate layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x30
  1       3     _not_used0 (Padding)
  4       1     century
  5       1     year
  6       1     month
  7       1     day
  8       1     hour
  9       1     minute
  10      23    _not_used1 (Padding)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  Total fields = 36 bytes + 1 checksum = 37 bytes

SetTimeDateResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x3, status nibble)
  1       35    _not_used0 (Padding)
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

# pylint: disable=duplicate-code
from paradox.hardware.spectra_magellan.parsers import SetTimeDate, SetTimeDateResponse


def _checksum(data: bytes) -> int:
    return sum(data) % 256


# ---------------------------------------------------------------------------
# SetTimeDate — BUILD tests
# ---------------------------------------------------------------------------


def test_build_set_time_date_basic():
    """Build SetTimeDate for a known date/time."""
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
    # padding at bytes 1-3 = 0x00
    assert raw[1:4] == b"\x00\x00\x00"
    # century at byte 4
    assert raw[4] == 20
    # year at byte 5
    assert raw[5] == 26
    # month at byte 6
    assert raw[6] == 2
    # day at byte 7
    assert raw[7] == 19
    # hour at byte 8
    assert raw[8] == 10
    # minute at byte 9
    assert raw[9] == 30
    # Total length = 37 bytes
    assert len(raw) == 37
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_set_time_date_total_length():
    """Total packet length = 37 bytes."""
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
    assert len(raw) == 37


def test_build_set_time_date_midnight():
    """Build SetTimeDate for midnight."""
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
    assert raw[8] == 0  # hour
    assert raw[9] == 0  # minute
    assert raw[-1] == _checksum(raw[:-1])


def test_build_set_time_date_end_of_year():
    """Build SetTimeDate for Dec 31."""
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
    assert raw[4] == 19  # century
    assert raw[5] == 99  # year
    assert raw[6] == 12  # month
    assert raw[7] == 31  # day
    assert raw[8] == 23  # hour
    assert raw[9] == 59  # minute
    assert raw[-1] == _checksum(raw[:-1])


def test_build_set_time_date_source_id_default():
    """source_id defaults to Winload_Direct = 1 at offset 33."""
    raw = SetTimeDate.build(
        {
            "fields": {
                "value": {
                    "century": 20,
                    "year": 26,
                    "month": 1,
                    "day": 1,
                    "hour": 0,
                    "minute": 0,
                }
            }
        }
    )
    assert raw[33] == 0x01  # source_id = Winload_Direct
    assert raw[34] == 0x00  # user_id low byte
    assert raw[35] == 0x00  # user_id high byte


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

    Byte 0: [7:4]=0x3 (command), [3]=reserved, [2]=alarm_reporting_pending,
            [1]=Winload_connected, [0]=NeWare_connected
    Bytes 1-35: _not_used0 = 0x00 * 35
    Byte 36: checksum
    """
    b0 = (0x3 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    data = bytes([b0]) + b"\x00" * 35
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_set_time_date_response_basic():
    """Parse basic SetTimeDateResponse with no status flags."""
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


def test_parse_set_time_date_response_neware_connected():
    """Parse SetTimeDateResponse with NeWare connected."""
    raw = _build_set_time_date_response(neware_connected=True)
    data = SetTimeDateResponse.parse(raw)

    assert data.fields.value.po.status.NeWare_connected is True


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
