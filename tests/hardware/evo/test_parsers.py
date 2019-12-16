from paradox.hardware.evo.parsers import DefinitionsParserMap


def test_zone_definition_test():
    parser = DefinitionsParserMap['zone']

    assert parser.sizeof() == 2

    data = parser.parse(b'\x11\x02')

    assert data.zone_definition == 'entry_delay1'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x31\x02')

    assert data.zone_definition == 'follow'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x41\x0a')

    assert data.zone_definition == 'instant'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True

    data = parser.parse(b'\x01\x0a')

    assert data.zone_definition == 'disabled'
    assert data.partition == 1
    assert data.options.alarm_type == 'steady_alarm'
    assert data.options.force_zone == True
    assert data.options.bypass_enabled == True