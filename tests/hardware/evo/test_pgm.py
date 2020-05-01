from binascii import hexlify, unhexlify

from paradox.hardware.evo.adapters import PGMFlags
from paradox.hardware.evo.parsers import (BroadcastRequest, BroadcastResponse,
                                          PerformPGMAction,
                                          PGMBroadcastCommand)


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
    payload = unhexlify("42070000000049")
