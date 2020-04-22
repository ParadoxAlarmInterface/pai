from paradox.lib.encodings import register_encodings

register_encodings()

def test_en_encoding():
    encoding = "paradox-en"
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"

    assert bytes([158]).decode(encoding) == "ä"
    assert bytes([206]).decode(encoding) == "Õ"
    assert bytes([131]).decode(encoding) == "Ü"


def test_ru_encoding():
    encoding = "paradox-ru"
    assert b"B".decode(encoding) == "B"

    assert b"0".decode(encoding) == "0"
