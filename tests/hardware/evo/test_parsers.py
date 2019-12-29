from paradox.hardware.evo.parsers import DefinitionsParserMap


def test_zone_definition_test():
    parser = DefinitionsParserMap['zone']

    assert parser.sizeof() == 2

    data = parser.parse(b'\x11\x02')

    assert data.definition == 'entry_delay1'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x31\x02')

    assert data.definition == 'follow'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x41\x0a')

    assert data.definition == 'instant'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x01\x0a')

    assert data.definition == 'disabled'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x42\x0e')

    assert data.definition == 'instant'
    assert data.partition == 2
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x42\x0e')

    assert data.definition == 'instant'
    assert data.partition == 2
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\xd4\x2a')

    assert data.definition == 'standard_fire_24h'
    assert data.partition == 4
    assert data.options.alarm_type == 'pulsed_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True


def test_partition_definition_test():
    parser = DefinitionsParserMap['partition']

    assert parser.sizeof() == 1

    data = parser.parse(b'\xcb')

    assert data[1]['definition'] == 'enabled'
    assert data[3]['definition'] == 'disabled'
    assert len(data) == 8
