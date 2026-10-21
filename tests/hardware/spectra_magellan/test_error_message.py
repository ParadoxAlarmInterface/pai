"""
Tests for Spectra/Magellan ErrorMessage (parse direction, panel -> PAI).

ErrorMessage layout:
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x7, status nibble)
  1       1     _not_used0 (Int8ub, default 0)
  2       1     message (Enum)
  3       33    _not_used1 (Padding)
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

import pytest

from paradox.hardware.spectra_magellan.parsers import ErrorMessage


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def _build_error_message(
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
    message_code=0x00,
):
    """
    Construct ErrorMessage bytes manually.

    Byte 0: [7:4]=0x7 (command), [3]=reserved, [2]=alarm_reporting_pending,
            [1]=Winload_connected, [0]=NeWare_connected
    Byte 1: _not_used0 = 0x00
    Byte 2: message (Enum byte)
    Bytes 3-35: _not_used1 = 0x00 * 33
    Byte 36: checksum
    """
    b0 = (0x7 << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    data = bytes([b0, 0x00, message_code]) + b"\x00" * 33
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_error_message_requested_command_failed():
    """Parse ErrorMessage with message = requested_command_failed (0x00)."""
    raw = _build_error_message(message_code=0x00)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.po.command == 0x7
    assert data.fields.value.message == "requested_command_failed"


def test_parse_error_message_invalid_user_code():
    """Parse ErrorMessage with message = invalid_user_code (0x01)."""
    raw = _build_error_message(message_code=0x01)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.message == "invalid_user_code"


def test_parse_error_message_panel_not_connected():
    """Parse ErrorMessage with message = panel_not_connected (0x10)."""
    raw = _build_error_message(message_code=0x10)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.message == "panel_not_connected"


def test_parse_error_message_invalid_pc_password():
    """Parse ErrorMessage with message = invalid_pc_password (0x12)."""
    raw = _build_error_message(message_code=0x12)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.message == "invalid_pc_password"


def test_parse_error_message_panel_already_connected():
    """Parse ErrorMessage with message = panel_already_connected (0x11)."""
    raw = _build_error_message(message_code=0x11)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.message == "panel_already_connected"


def test_parse_error_message_winload_connected_flag():
    """Parse ErrorMessage with Winload_connected status flag."""
    raw = _build_error_message(winload_connected=True, message_code=0x05)
    data = ErrorMessage.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.message == "panel_will_disconnect"


@pytest.mark.parametrize(
    "code,expected_name",
    [
        (0x00, "requested_command_failed"),
        (0x01, "invalid_user_code"),
        (0x02, "partition_in_code_lockout"),
        (0x05, "panel_will_disconnect"),
        (0x10, "panel_not_connected"),
        (0x11, "panel_already_connected"),
        (0x12, "invalid_pc_password"),
        (0x13, "winload_on_phone_line"),
        (0x14, "invalid_module_address"),
        (0x15, "cannot_write_in_ram"),
        (0x16, "upgrade_request_fail"),
        (0x17, "record_number_out_of_range"),
        (0x19, "invalid_record_type"),
        (0x1A, "multibus_not_supported"),
        (0x1B, "incorrect_number_of_users"),
        (0x1C, "invalid_label_number"),
    ],
)
def test_parse_error_message_all_codes(code, expected_name):
    """Verify all defined error codes parse to their correct enum names."""
    raw = _build_error_message(message_code=code)
    data = ErrorMessage.parse(raw)
    assert str(data.fields.value.message) == expected_name
