import pytest

from paradox.lib.encodings import register_encodings, ru

from paradox.lib.encodings.charmaps import en

register_encodings()

test_data_en = [
    (b"B", "B"),
    (b"0", "0"),
    (b"z", "z"),
    (bytes([131]), "Ü"),
    (bytes([142]), "ö"),
    (bytes([148]), "ê"),
    (bytes([151]), "ë"),
    (bytes([153]), "Ä"),
    (bytes([158]), "ä"),
    (bytes([159]), "ª"),
    (bytes([161]), "î"),
    (bytes([162]), "ì"),
    (bytes([163]), "í"),
    (bytes([164]), "ï"),
    (bytes([177]), "±"),
    (bytes([183]), "£"),
    (bytes([185]), " "),
    (bytes([186]), " "),
    (bytes([206]), "Õ"),
    (bytes([207]), "õ"),
]


@pytest.mark.parametrize("raw,expected", test_data_en)
def test_en_encoding(raw, expected):
    encoding = "paradox-en"
    assert len(expected) == 1

    assert raw.decode(encoding) == expected, f"char {ord(raw)} != {expected}"


def test_en_encoding_len():
    assert len(en.charmap) == 256


test_data_ru = [
    (b"B", "В"),  # 0x0412 instead of the normal B. Why? I don't know. ;)
    (b"0", "0"),
    (b"z", "z"),
    (bytes([160]), "Б"),
    (bytes([199]), "я"),
    (bytes([230]), "щ"),
]


@pytest.mark.parametrize("raw,expected", test_data_ru)
def test_ru_encoding(raw, expected):
    encoding = "paradox-ru"
    assert len(expected) == 1

    assert raw.decode(encoding) == expected, f"char {ord(raw)} != {expected}"


def test_ru_encoding_len():
    assert len(ru.decoding_table) == 256
