"""
Tests for EVO InitializeCommunication (build) and LoginConfirmationResponse (parse).

EVO InitializeCommunication layout (build direction, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x00
  1       1     module_address = 0x00 (default)
  2       2     _not_used0 (padding)
  4       1     product_id
  5       1     firmware.version
  6       1     firmware.revision
  7       1     firmware.build
  8       2     panel_id (Int16ub)
  10      2     pc_password (default b"0000")
  12      1     modem_speed
  13      1     source_method (default 0x00 = Winload_Connection)
  14      3     user_code (Int24ub, default 0x000000)
  17      4     serial_number
  21      10    system_options (BitsSwapped BitStruct, 80 bits)
  31      4     _not_used1 (padding)
  35      1     source_id (default 1 = Winload_Direct)
  36      1     carrier_length
  Total = 36 bytes fields + 1 byte checksum = 37 bytes

LoginConfirmationResponse layout (parse direction, panel -> PAI):
  Offset  Size  Field
  0       1     po (BitStruct: command nibble=0x1, status nibble)
  1       1     length (PacketLength = 6)
  2       1     result (BitStruct: _not_used0[3], neware_answer, _not_used1[4])
  3       2     callback (Int16ub)
  Total fields = 5 bytes + 1 byte checksum = 6 bytes
"""

# pylint: disable=duplicate-code
import pytest

from paradox.hardware.evo.parsers import (
    InitializeCommunication,
    LoginConfirmationResponse,
)


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def _minimal_system_options():
    """Return minimal system_options dict with all flags set to False/0."""
    return {
        "pgm1_smoke": False,
        "no_bell_cut_off": False,
        "daylight_saving_time": False,
        "shabbat_feature": False,
        "battery_charge_current": False,
        "ac_failure_not_displayed_as_trouble": False,
        "clear_bell_limit_trouble": False,
        "combus_speed": False,
        "partitions": {},
        "siren_output_partition": {},
        "multiple_actions_user_menu": False,
        "user_code_length_flexible": False,
        "user_code_length_6": False,
        "power_save_mode": False,
        "bypass_not_displayed_when_armed": False,
        "trouble_latch": False,
        "eol_resistor_on_harwire_zones": False,
        "atz": False,
        "wireless_transmitter_supervision_options": 0,
        "generate_supervision_failure_on_bypassed_wireless_zone": False,
        "restrict_arming_on_wireless_transmitter_supervision_failure": False,
        "tamper_recognition_options": 0,
        "generate_tamper_if_detected_on_bypassed_zone": False,
        "restrict_arming_on_tamper": False,
        "restrict_arming_on_ac_failure": False,
        "restrict_arming_on_battery_failure": False,
        "restrict_arming_on_bell_or_aux_failure": False,
        "restrict_arming_on_tlm_failure": False,
        "restrict_arming_on_module_troubles": False,
        "account_number_transmission": False,
        "transmit_zone_status_on_serial_port": False,
        "serial_port_baud_rate_57600": False,
        "telephone_line_monitoring": 0,
        "dialer_reporting": False,
        "dialing_method": False,
        "pulse_ratio": False,
        "busy_tone_detection": False,
        "switch_to_pulse_dialing": False,
        "bell_siren_upon_communication_failure": False,
        "call_back": False,
        "automatic_event_buffer_transmission": False,
        "autotest_report_transmission_options": 0,
        "keypad_beep_on_successful_arming_disarming_report": False,
        "alternate_dialing": False,
        "dial_tone_delay": False,
        "report_zone_restore": False,
        "access_control_feature": False,
        "log_request_for_exit": False,
        "log_door_left_open_restore": False,
        "log_door_forced_restore": False,
        "bulglar_alarm_on_forced_door": False,
        "skip_exit_delay_when_arming_with_access_card": False,
        "bulglar_alarm_on_door_left_open": False,
        "who_has_access_during_clock_loss": False,
    }


def _build_init_comm(**kwargs):
    """Helper to build InitializeCommunication with sensible defaults."""
    value = {
        "product_id": "DIGIPLEX_EVO_48",
        "firmware": {"version": 7, "revision": 21, "build": 0},
        "panel_id": 0x0000,
        "pc_password": b"\x00\x00",
        "modem_speed": b"\x00",
        "serial_number": b"\x00\x00\x00\x00",
        "system_options": _minimal_system_options(),
        "carrier_length": b"\x00",
    }
    value.update(kwargs)
    return InitializeCommunication.build({"fields": {"value": value}})


# ---------------------------------------------------------------------------
# InitializeCommunication — BUILD tests
# ---------------------------------------------------------------------------


def test_build_initialize_communication_command_byte():
    """First byte must be command 0x00."""
    raw = _build_init_comm()
    assert raw[0] == 0x00


def test_build_initialize_communication_total_length():
    """Total packet length = 37 bytes (36 fields + 1 checksum)."""
    raw = _build_init_comm()
    assert len(raw) == 37


def test_build_initialize_communication_checksum_validity():
    """Checksum is always sum-of-fields-bytes mod 256."""
    raw = _build_init_comm()
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_product_id_evo48():
    """Build sets product_id correctly for EVO48."""
    raw = _build_init_comm(product_id="DIGIPLEX_EVO_48")
    # product_id DIGIPLEX_EVO_48 = 3, at offset 4
    assert raw[4] == 3
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_product_id_evo96():
    """Build sets product_id correctly for EVO96."""
    raw = _build_init_comm(product_id="DIGIPLEX_EVO_96")
    assert raw[4] == 4
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_product_id_evo192():
    """Build sets product_id correctly for EVO192."""
    raw = _build_init_comm(product_id="DIGIPLEX_EVO_192")
    assert raw[4] == 5
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_firmware():
    """Build encodes firmware version/revision/build."""
    raw = _build_init_comm(firmware={"version": 7, "revision": 21, "build": 3})
    assert raw[5] == 7  # version at offset 5
    assert raw[6] == 21  # revision at offset 6
    assert raw[7] == 3  # build at offset 7
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_panel_id():
    """Build encodes panel_id big-endian at offsets 8-9."""
    raw = _build_init_comm(panel_id=0x1234)
    assert raw[8] == 0x12
    assert raw[9] == 0x34
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_source_method_winload():
    """Build default source_method = Winload_Connection (0x00) at offset 13."""
    raw = _build_init_comm()
    # modem_speed at offset 12, source_method at offset 13
    assert raw[13] == 0x00
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_source_method_neware():
    """Build sets source_method to NEware_Connection (0x55) at offset 13."""
    raw = _build_init_comm(source_method="NEware_Connection")
    assert raw[13] == 0x55
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_module_address_default():
    """module_address defaults to 0x00."""
    raw = _build_init_comm()
    assert raw[1] == 0x00


@pytest.mark.parametrize(
    "product_id,expected_byte",
    [
        ("DIGIPLEX_EVO_48", 3),
        ("DIGIPLEX_EVO_96", 4),
        ("DIGIPLEX_EVO_192", 5),
        ("DIGIPLEX_EVO_HD", 7),
    ],
)
def test_build_initialize_communication_product_ids(product_id, expected_byte):
    """Build correctly encodes various EVO product IDs."""
    raw = _build_init_comm(product_id=product_id)
    assert raw[4] == expected_byte
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# LoginConfirmationResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_login_confirmation_response(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    command_nibble=0x1,
    reserved=False,
    alarm_reporting_pending=False,
    winload_connected=False,
    neware_connected=False,
    neware_answer=False,
    callback=0x0000,
):
    """
    Construct a LoginConfirmationResponse byte sequence manually.

    Byte 0: [7:4] command_nibble=0x1, [3] reserved, [2] alarm_reporting_pending,
            [1] Winload_connected, [0] NeWare_connected
    Byte 1: length = 6 (5 fields bytes + 1 checksum)
    Byte 2: [7:5] 0, [4] neware_answer, [3:0] 0
    Bytes 3-4: callback big-endian
    Byte 5: checksum
    """
    b0 = (command_nibble << 4) | (
        (int(reserved) << 3)
        | (int(alarm_reporting_pending) << 2)
        | (int(winload_connected) << 1)
        | int(neware_connected)
    )
    length = 6  # fields.sizeof() + checksum.sizeof() = 5 + 1
    b2 = int(neware_answer) << 4  # neware_answer at bit 4 (3 unused bits before it)
    b3 = (callback >> 8) & 0xFF
    b4 = callback & 0xFF
    data = bytes([b0, length, b2, b3, b4])
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_login_confirmation_response_basic():
    """Parse a simple LoginConfirmationResponse with no flags set."""
    raw = _build_login_confirmation_response()
    data = LoginConfirmationResponse.parse(raw)

    assert data.fields.value.po.command == 0x1
    assert data.fields.value.po.status.reserved is False
    assert data.fields.value.po.status.alarm_reporting_pending is False
    assert data.fields.value.po.status.Winload_connected is False
    assert data.fields.value.po.status.NeWare_connected is False
    assert data.fields.value.result.neware_answer is False
    assert data.fields.value.callback == 0x0000


def test_parse_login_confirmation_response_winload_connected():
    """Parse response indicating Winload is connected."""
    raw = _build_login_confirmation_response(winload_connected=True)
    data = LoginConfirmationResponse.parse(raw)

    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is False


def test_parse_login_confirmation_response_neware_answer():
    """Parse response with neware_answer flag set."""
    raw = _build_login_confirmation_response(neware_answer=True)
    data = LoginConfirmationResponse.parse(raw)

    assert data.fields.value.result.neware_answer is True


def test_parse_login_confirmation_response_callback_nonzero():
    """Parse response with a non-zero callback value."""
    raw = _build_login_confirmation_response(callback=0x1234)
    data = LoginConfirmationResponse.parse(raw)

    assert data.fields.value.callback == 0x1234


def test_parse_login_confirmation_response_all_status_flags():
    """Parse response with all status flags set."""
    raw = _build_login_confirmation_response(
        reserved=True,
        alarm_reporting_pending=True,
        winload_connected=True,
        neware_connected=True,
        neware_answer=True,
        callback=0xFFFF,
    )
    data = LoginConfirmationResponse.parse(raw)

    assert data.fields.value.po.status.reserved is True
    assert data.fields.value.po.status.alarm_reporting_pending is True
    assert data.fields.value.po.status.Winload_connected is True
    assert data.fields.value.po.status.NeWare_connected is True
    assert data.fields.value.result.neware_answer is True
    assert data.fields.value.callback == 0xFFFF
