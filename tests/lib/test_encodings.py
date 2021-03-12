import pytest

from paradox.lib.encodings import register_encodings

from paradox.lib.encodings.charmaps import en, ru, el, ar, he

register_encodings()

# ENGLISH

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

# RUSSIAN

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
    assert len(ru.charmap) == 256

# GREEK

test_data_el = [
    (b"B", "B"),
    (b"0", "0"),
    (b"z", "z"),
    (bytes(  [1]), "Δ"),
    (bytes([212]), "Γ"),
    (bytes([228]), "ζ"),
    (bytes([244]), "ω"),
]


@pytest.mark.parametrize("raw,expected", test_data_el)
def test_el_encoding(raw, expected):
    encoding = "paradox-el"
    assert len(expected) == 1

    assert raw.decode(encoding) == expected, f"char {ord(raw)} != {expected}"


def test_el_encoding_len():
    assert len(el.charmap) == 256


# ARABIC

test_data_ar = [
    (b"B", "B"),
    (b"0", "0"),
    (b"z", "z"),
    (bytes( [94]), " "),
    (bytes([128]), "ب"),
    (bytes([228]), "د"),
    (bytes([244]), "أ"),
]


@pytest.mark.parametrize("raw,expected", test_data_ar)
def test_ar_encoding(raw, expected):
    encoding = "paradox-ar"
    assert len(expected) == 1

    assert raw.decode(encoding) == expected, f"char {ord(raw)} != {expected}"


def test_ar_encoding_len():
    assert len(el.charmap) == 256


# HEBREW

test_data_he = [
    (b"B", "B"),
    (b"0", "0"),
    (b"z", "z"),
    (bytes( [94]), " "),
    (bytes([160]), "א"),
    (bytes([175]), "ן"),
    (bytes([186]), "ת"),
]


@pytest.mark.parametrize("raw,expected", test_data_he)
def test_he_encoding(raw, expected):
    encoding = "paradox-he"
    assert len(expected) == 1

    assert raw.decode(encoding) == expected, f"char {ord(raw)} != {expected}"


def test_he_encoding_len():
    assert len(el.charmap) == 256
