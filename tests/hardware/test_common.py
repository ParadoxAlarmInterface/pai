from construct import Struct

from paradox.hardware.common import HexInt

def test_HexInt_parse():
    assert HexInt.parse(b'\x91') == 91

def test_application_version():
    version = b'\x06\x90\x05'

    parsed = Struct("version" / HexInt, "revision" / HexInt, "build" / HexInt).parse(version)

    assert parsed == {"version": 6, "revision": 90, "build": 5}

def test_wrong_HexInt_parse():
    assert HexInt.parse(b'\xa0') == -1

def test_HexInt_build():
    assert HexInt.build(91) == b'\x91'
