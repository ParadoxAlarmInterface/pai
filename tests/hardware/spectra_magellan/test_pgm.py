from paradox.hardware.spectra_magellan.parsers import DefinitionsParserMap
from paradox.hardware.spectra_magellan.adapters import PGMDefinitionAdapter

def test_pgm_definitions_1():
    parser = DefinitionsParserMap['pgm'].parse(b'\x00\x00\x00\x00\x00\x00')
    assert parser.get('definition') == 'disabled'

def test_pgm_definitions_2():
    parser = DefinitionsParserMap['pgm'].parse(b'\x65\x00\x00\x00\x00\x00')
    assert parser.get('definition') == {'activation': 'unknown', 'deactivation': 'disabled'}

def test_pgm_definitions_3():
    parser = DefinitionsParserMap['pgm'].parse(b'\x65\x00\x00\x65\x00\x00')
    assert parser.get('definition') == {'activation': 'unknown', 'deactivation': 'unknown'}

def test_pgm_definitions_4():
    parser = DefinitionsParserMap['pgm'].parse(b'\x00\x01\x00\x01\x02\x00')
    assert parser.get('definition') == {'activation': PGMDefinitionAdapter.PGMEvent.zone_ok, 'deactivation': PGMDefinitionAdapter.PGMEvent.zone_open}
