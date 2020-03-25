import codecs

from paradox.lib.encodings import paradox_codec_search


def test_en_encoding():
    encoding = "paradox-en"
    codecs.register(paradox_codec_search)
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"


def test_ru_encoding():
    encoding = "paradox-ru"
    codecs.register(paradox_codec_search)
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"
