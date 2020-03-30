from paradox.lib.encodings import register_encodings

register_encodings()

def test_en_encoding():
    encoding = "paradox-en"
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"


def test_ru_encoding():
    encoding = "paradox-ru"
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"
