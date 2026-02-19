"""
Tests for Spectra/Magellan PerformAction (build) and PerformActionResponse (parse).

PerformAction layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x40
  1       1     _not_used0 (Padding)
  2       1     action (Enum)
  3       1     argument (Enum)
  4       1     instant (Flag, default False = 0x00)
  5       28    _not_used1 (Padding)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  Total fields = 36 bytes + 1 checksum = 37 bytes

PerformActionResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x4, status nibble)
  1       1     _not_used0 (Padding)
  2       1     action (Enum)
  3       33    _not_used1 (Padding)
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

# pylint: disable=duplicate-code
from binascii import unhexlify

import pytest

from paradox.hardware.spectra_magellan.parsers import (
    PerformAction,
    PerformActionResponse,
)


def _checksum(data: bytes) -> int:
    return sum(data) % 256


# ---------------------------------------------------------------------------
# PerformAction — BUILD tests
# ---------------------------------------------------------------------------


def test_build_perform_action_full_arm():
    """Build PerformAction with Full_Arm action."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "Full_Arm",
                    "argument": "One_Beep",
                }
            }
        }
    )

    # command = 0x40 at byte 0
    assert raw[0] == 0x40
    # action = Full_Arm = 0x04 at byte 2
    assert raw[2] == 0x04
    # argument = One_Beep = 0x04 at byte 3
    assert raw[3] == 0x04
    # Total length = 37 bytes
    assert len(raw) == 37
    # checksum
    assert raw[-1] == _checksum(raw[:-1])


def test_build_perform_action_disarm():
    """Build PerformAction with Disarm action."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "Disarm",
                    "argument": "Accept_Beep",
                }
            }
        }
    )

    assert raw[0] == 0x40
    # Disarm = 0x05
    assert raw[2] == 0x05
    # Accept_Beep = 0x10
    assert raw[3] == 0x10
    assert raw[-1] == _checksum(raw[:-1])


def test_build_perform_action_stay_arm():
    """Build PerformAction with Stay_Arm action."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "Stay_Arm",
                    "argument": "One_Beep",
                }
            }
        }
    )

    # Stay_Arm = 0x01
    assert raw[2] == 0x01
    assert raw[-1] == _checksum(raw[:-1])


def test_build_perform_action_pgm_on():
    """Build PerformAction with PGM_On action."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "PGM_On",
                    "argument": "One_Beep",
                }
            }
        }
    )

    # PGM_On = 0x32
    assert raw[2] == 0x32
    assert raw[-1] == _checksum(raw[:-1])


def test_build_perform_action_pgm_off():
    """Build PerformAction with PGM_Off action."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "PGM_Off",
                    "argument": "One_Beep",
                }
            }
        }
    )

    # PGM_Off = 0x33
    assert raw[2] == 0x33
    assert raw[-1] == _checksum(raw[:-1])


def test_build_perform_action_total_length():
    """Total packet length = 37 bytes."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "Full_Arm",
                    "argument": "One_Beep",
                }
            }
        }
    )
    assert len(raw) == 37


def test_build_perform_action_instant():
    """Build PerformAction with instant=True."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": "Full_Arm",
                    "argument": "One_Beep",
                    "instant": True,
                }
            }
        }
    )

    # instant = True = 0x01 at byte 4
    assert raw[4] == 0x01
    assert raw[-1] == _checksum(raw[:-1])


@pytest.mark.parametrize(
    "action_name,action_code",
    [
        ("Stay_Arm", 0x01),
        ("Stay_Arm1", 0x02),
        ("Sleep_Arm", 0x03),
        ("Full_Arm", 0x04),
        ("Disarm", 0x05),
        ("Bypass", 0x10),
        ("Reload_RAM", 0x80),
        ("Bus_Scan", 0x85),
    ],
)
def test_build_perform_action_various_actions(action_name, action_code):
    """Various action codes are encoded correctly."""
    raw = PerformAction.build(
        {
            "fields": {
                "value": {
                    "action": action_name,
                    "argument": "One_Beep",
                }
            }
        }
    )
    assert raw[2] == action_code
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# PerformActionResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_perform_action_response(
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
    action_code=0x04,
):
    """
    Construct PerformActionResponse bytes manually.

    Byte 0: [7:4]=0x4 (command), [3]=reserved, [2]=alarm_reporting_pending,
            [1]=Winload_connected, [0]=NeWare_connected
    Byte 1: _not_used0 = 0x00
    Byte 2: action (Enum byte)
    Bytes 3-35: _not_used1 = 0x00 * 33
    Byte 36: checksum
    """
    b0 = (0x4 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    data = bytes([b0, 0x00, action_code]) + b"\x00" * 33
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_perform_action_response_full_arm():
    """Parse PerformActionResponse for Full_Arm."""
    raw = _build_perform_action_response(action_code=0x04)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.command == 0x4
    assert data.fields.value.action == "Full_Arm"


def test_parse_perform_action_response_disarm():
    """Parse PerformActionResponse for Disarm."""
    raw = _build_perform_action_response(action_code=0x05)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.action == "Disarm"


def test_parse_perform_action_response_winload_connected():
    """Parse PerformActionResponse with Winload connected."""
    raw = _build_perform_action_response(winload_connected=True, action_code=0x04)
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True


def test_parse_perform_action_response_all_status_flags():
    """Parse PerformActionResponse with all status flags set."""
    raw = _build_perform_action_response(
        reserved=True,
        alarm_reporting_pending=True,
        winload_connected=True,
        neware_connected=True,
        action_code=0x04,
    )
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.status.reserved is True
    assert data.fields.value.po.status.alarm_reporting_pending is True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is True


def test_parse_perform_action_response_known_capture():
    """
    Verify parsing of a known-good capture from test_partition_control.py:
    b"42000400...0046" is a 37-byte PerformActionResponse with Full_Arm.

    Byte 0 = 0x42: command nibble=0x4, status nibble=0x2 (Winload_connected=True)
    Byte 2 = 0x04: action = Full_Arm
    """
    raw = unhexlify(
        "42000400000000000000000000000000000000000000000000000000000000000000000046"
    )
    data = PerformActionResponse.parse(raw)

    assert data.fields.value.po.command == 0x4
    # byte 0 = 0x42: status nibble = 0x2 → Winload_connected = True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.action == "Full_Arm"
