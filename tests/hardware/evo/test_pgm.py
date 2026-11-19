import pytest
from binascii import unhexlify

from paradox.hardware.evo.adapters import PGMFlags
from paradox.hardware.evo.parsers import PerformActionResponse, PerformPGMAction


def test_pgm3_activate_and_monitor():
    expected_out = unhexlify("40130600000004000000000000000300000060")

    pgms = [3]

    a = PerformPGMAction.build({"fields": {"value": {"pgms": pgms, "command": "on"}}})

    assert a == expected_out


def test_pgm3_activate_until_released():
    expected_out = unhexlify("40130600000004000000000000000400000061")

    pgms = [3]

    a = PerformPGMAction.build(
        {"fields": {"value": {"pgms": pgms, "command": "on_override"}}}
    )

    assert a == expected_out


def test_pgm3_deactivate_until_released():
    expected_out = unhexlify("4013060000000400000000000000020000005f")

    pgms = [3]

    a = PerformPGMAction.build(
        {"fields": {"value": {"pgms": pgms, "command": "off_override"}}}
    )

    assert a == expected_out


def test_pgm3_deactivate_and_monitor():
    expected_out = unhexlify("4013060000000400000000000000010000005e")

    pgms = [3]

    a = PerformPGMAction.build({"fields": {"value": {"pgms": pgms, "command": "off"}}})

    assert a == expected_out


def test_pgm4_activate_and_monitor():
    expected_out = unhexlify("40130600000008000000000000000300000064")

    pgms = [4]

    a = PerformPGMAction.build({"fields": {"value": {"pgms": pgms, "command": "on"}}})

    assert a == expected_out


def test_pgm4_deactivate_and_monitor():
    expected_out = unhexlify("40130600000008000000000000000100000062")

    pgms = [4]

    a = PerformPGMAction.build({"fields": {"value": {"pgms": pgms, "command": "off"}}})

    assert a == expected_out


def test_pgm5_activate_and_monitor():
    # PGM 5 maps to bit 4 of the bitmap (byte offset 6 = 0x10).
    # Onboard PGM 5 is the only dry relay on the EVO192 mainboard; see
    # https://github.com/ParadoxAlarmInterface/pai/issues/580
    expected_out = unhexlify("4013060000001000000000000000030000006c")

    pgms = [5]

    a = PerformPGMAction.build({"fields": {"value": {"pgms": pgms, "command": "on"}}})

    assert a == expected_out


def test_pgm_flags_1():
    parser = PGMFlags(1)
    assert parser.sizeof() == 4

    a = parser.parse(unhexlify("90000000"))

    print(a)

    assert a[1].disabled is False
    assert a[1].on is False
    assert a[1].normally_closed is False
    assert a[1].timer_active is False
    assert a[1].time_left == 0
    assert a[1].fire_2_wires is True


def test_pgm_flags_2():
    parser = PGMFlags(1)
    assert parser.sizeof() == 4

    a = parser.parse(unhexlify("21000000"))

    print(a)

    assert a[1].disabled is True
    assert a[1].on is True
    assert a[1].normally_closed is False
    assert a[1].timer_active is False
    assert a[1].time_left == 0
    assert a[1].fire_2_wires is False


def test_pgm_flags_3():
    parser = PGMFlags(1)
    assert parser.sizeof() == 4

    a = parser.parse(unhexlify("534c0200"))

    print(a)

    assert a[1].disabled is False
    assert a[1].on is True
    assert a[1].normally_closed is True
    assert a[1].timer_active is True
    assert a[1].time_left == 9 * 60 + 48
    assert a[1].fire_2_wires is False


def test_pgm_confirmation():
    raw = unhexlify("42070000000049")
    parsed = PerformActionResponse.parse(raw)

    assert parsed.fields.value.po.command == 0x4
    assert parsed.fields.value.po.status.Winload_connected is True
    assert parsed.fields.value.po.status.alarm_reporting_pending is False
    assert parsed.fields.value.packet_length == 7


def test_panel_pgm_action_packet():
    from paradox.hardware.evo.parsers import PerformPanelPGMAction

    commands = ["release"] * 64
    commands[4] = "on_override"
    raw = PerformPanelPGMAction.build({"fields": {"value": {"pgm_commands": commands}}})

    assert raw == unhexlify("a447000000000000000004" + "00" * 59 + "ef")


@pytest.mark.parametrize(
    "version,revision,expected",
    [
        (4, 0x74, "PerformPanelPGMAction"),
        (4, 0x75, "PerformPGMAction"),
        (7, 0x15, "PerformPGMAction"),
        (2, 0x80, "PerformPanelPGMAction"),
    ],
)
async def test_control_outputs_command_by_firmware(mocker, version, revision, expected):
    from paradox.hardware.evo.panel import Panel_EVOBase
    from paradox.hardware.evo import parsers

    panel = Panel_EVOBase.__new__(Panel_EVOBase)
    panel.core = mocker.MagicMock()
    panel.core.send_wait = mocker.AsyncMock(return_value=object())
    panel.settings = mocker.MagicMock()
    panel.settings.firmware.version = version
    panel.settings.firmware.revision = revision

    assert await panel.control_outputs([5], "on_override")
    assert panel.core.send_wait.call_count == 1
    assert panel.core.send_wait.call_args.args[0] is getattr(parsers, expected)
