from construct import Bitwise, Struct, this, Flag, Computed, Default

from paradox.hardware.evo.adapters import DictArray

TestParser = Bitwise(
        DictArray(8, 1, Struct(
                "_index" / Computed(this._index + 1),
                "enabled" / Default(Flag, False)
            ))
    )

TestParser2 = Bitwise(
        DictArray(8, 65, Struct(
                "_index" / Computed(this._index + 65),
                "enabled" / Default(Flag, False)
            ))
    )

TestPickerParser = Bitwise(
        DictArray(8, 1, Struct(
                "_index" / Computed(this._index + 1),
                "enabled" / Default(Flag, False)
            ), pick_key="enabled")
    )

def test_index_parsing():
    r = TestParser.parse(b'\x02')

    assert r[8].enabled == False
    assert r[7].enabled == True
    assert r[8].enabled == False


def test_index_building():
    r = TestParser.build({
        1: {"enabled": False},
        2: {"enabled": False},
        3: {"enabled": False},
        4: {"enabled": False},
        5: {"enabled": False},
        6: {"enabled": False},
        7: {"enabled": True},
        8: {"enabled": False},
    })

    assert r == b'\x02'

def test_index_partial_building():
    r = TestParser.build({
        7: {"enabled": True},
    })

    assert r == b'\x02'

def test_large_index_partial_parsing():
    r = TestParser2.parse(b'\x02')

    assert r[70].enabled == False
    assert r[71].enabled == True
    assert r[72].enabled == False

def test_large_index_partial_building():
    r = TestParser2.build({
        71: {"enabled": True},
    })

    assert r == b'\x02'


def test_picker_large_index_partial_parsing():
    r = TestParser2.parse(b'\x02')

    assert r[70].enabled == False
    assert r[71].enabled == True
    assert r[72].enabled == False


def test_picker_building():
    r = TestPickerParser.build({
        7: True,
    })

    assert r == b'\x02'

def test_picker_parsing():
    r = TestPickerParser.parse(b'\x02')

    assert r[6] is False
    assert r[7] is True
    assert r[8] is False

    assert isinstance(r[6], bool)
    assert isinstance(r[7], bool)
    assert isinstance(r[8], bool)

