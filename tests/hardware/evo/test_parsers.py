import binascii

from construct import Container
from paradox.hardware.evo.parsers import (DefinitionsParserMap,
                                          get_user_definition)


def test_zone_definition_test():
    parser = DefinitionsParserMap["zone"]

    assert parser.sizeof() == 2

    data = parser.parse(b"\x11\x02")

    assert data.definition == "entry_delay1"
    assert data.partition == 1
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\x31\x02")

    assert data.definition == "follow"
    assert data.partition == 1
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\x41\x0a")

    assert data.definition == "instant"
    assert data.partition == 1
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.force_zone is True
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\x01\x0a")

    assert data.definition == "disabled"
    assert data.partition == 1
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.force_zone is True
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\x42\x0e")

    assert data.definition == "instant"
    assert data.partition == 2
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.force_zone is True
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\x42\x0e")

    assert data.definition == "instant"
    assert data.partition == 2
    assert data.options.alarm_type == "steady_alarm"
    assert data.options.force_zone is True
    assert data.options.bypass_enabled is True

    data = parser.parse(b"\xd4\x2a")

    assert data.definition == "standard_fire_24h"
    assert data.partition == 4
    assert data.options.alarm_type == "pulsed_alarm"
    assert data.options.force_zone is True
    assert data.options.bypass_enabled is True


def test_partition_definition_test():
    parser = DefinitionsParserMap["partition"]

    assert parser.sizeof() == 1

    data = parser.parse(b"\xcb")

    assert data[1]["definition"] == "enabled"
    assert data[3]["definition"] == "disabled"
    assert len(data) == 8


def test_user_definition_test():
    settings = Container(
        system_options=Container(
            user_code_length_6=False, user_code_length_flexible=False
        )
    )

    parser = get_user_definition(settings)

    assert parser.sizeof() == 10

    data = parser.parse(binascii.unhexlify("00000048000000000000"))
    assert data.code is None

    # master
    data = parser.parse(binascii.unhexlify("123412ebff00af000000"))

    assert data.code == "1234"
    assert data.options == dict(
        type="FullMaster",
        duress=False,
        bypass=True,
        arm_only=False,
        stay_instant_arming=True,
        force_arming=True,
        all_subsystems=True,
    )
    assert data.partitions == {
        1: True,
        2: True,
        3: True,
        4: True,
        5: True,
        6: True,
        7: True,
        8: True,
    }

    # regular
    data = parser.parse(binascii.unhexlify("a123a140cb0000000000"))

    assert data.code == "0123"
    assert data.options == dict(
        type="Regular",
        duress=False,
        bypass=False,
        arm_only=False,
        stay_instant_arming=False,
        force_arming=True,
        all_subsystems=False,
    )
    assert data.partitions == {
        1: True,
        2: True,
        3: False,
        4: True,
        5: False,
        6: False,
        7: True,
        8: True,
    }
