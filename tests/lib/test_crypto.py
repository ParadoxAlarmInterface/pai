import pytest

from paradox.lib.crypto import decrypt, encrypt

dec_text = b"Very hard text to be encrypted"
enc_text = b'\xe2\x14S\x8eW`v\xaaa\xc5=\xfe\x90\x94\xf2\x97\xf0\x1f\x19I\xf1\xa7"h\xe5*\xe8\x01\xd4\xdczk'
password = b"test123456"

# Captured from the pure-Python implementation at dc9384b, not a round trip
# through the replacement. Keys are bytes(range(key_length)); plaintext bytes
# are (i * 17 + 128) % 256, exercising non-ASCII values and block boundaries.
LEGACY_VECTORS = [
    (1, 1, "f8be147ccc9b5912d789511c9122f654"),
    (4, 15, "e8372aa0ffa5c8f82b6ef9b883f697dd"),
    (16, 16, "ded436281386267d63c30cec078e6417"),
    (
        31,
        17,
        "6eef218f895ae3af5fcb285bfe2693f50611ee368918a34f1ad060bd4f8d78b9",
    ),
    (
        32,
        32,
        "3216339851365de6ab392dfa293e0424cacd239197de3a28289130ba5e02556f",
    ),
    (
        33,
        37,
        "3216339851365de6ab392dfa293e0424cacd239197de3a28289130ba5e02556f"
        "de43455351bfc337b06ec5aaade97e83",
    ),
    (
        64,
        48,
        "3216339851365de6ab392dfa293e0424cacd239197de3a28289130ba5e02556f"
        "4bfce16b00b59cebf0d73381b58427ef",
    ),
]


def test_encrypt():
    assert encrypt(dec_text, password) == enc_text


def test_decrypt():
    assert decrypt(enc_text, password) == dec_text + b"\xee" * 2


@pytest.mark.parametrize("key_length,data_length,ciphertext", LEGACY_VECTORS)
def test_legacy_vectors(key_length, data_length, ciphertext):
    key = bytes(range(key_length))
    plaintext = bytes((i * 17 + 128) % 256 for i in range(data_length))
    expected = bytes.fromhex(ciphertext)
    assert encrypt(plaintext, key) == expected
    assert decrypt(expected, key) == plaintext + b"\xee" * (-data_length % 16)


@pytest.mark.parametrize("data_type", [bytes, bytearray, memoryview, list, tuple])
def test_byte_inputs_are_not_mutated(data_type):
    plaintext = data_type(dec_text)
    ciphertext = data_type(enc_text)
    assert encrypt(plaintext, password) == enc_text
    assert decrypt(ciphertext, password) == dec_text + b"\xee" * 2
    assert bytes(plaintext) == dec_text
    assert bytes(ciphertext) == enc_text
    assert type(encrypt(plaintext, password)) is bytes
    assert type(decrypt(ciphertext, password)) is bytes


@pytest.mark.parametrize("key_type", [bytes, memoryview, tuple])
def test_full_length_key_types(key_type):
    key = key_type(bytes(range(32)))
    plaintext = bytes((i * 17 + 128) % 256 for i in range(32))
    ciphertext = bytes.fromhex(LEGACY_VECTORS[4][2])
    assert encrypt(plaintext, key) == ciphertext
    assert decrypt(ciphertext, key) == plaintext
    assert bytes(key) == bytes(range(32))


@pytest.mark.parametrize("length", range(16))
def test_decrypt_ignores_partial_tail(length):
    tail = bytes(range(length))
    assert decrypt(enc_text + tail, password) == dec_text + b"\xee" * 2
    assert decrypt(tail, password) == b""


@pytest.mark.parametrize("operation", [encrypt, decrypt])
def test_empty_input(operation):
    assert operation(b"", password) == b""


@pytest.mark.parametrize("operation", [encrypt, decrypt])
@pytest.mark.parametrize("data", [b"", b"123", bytes(range(16))])
def test_empty_key_is_rejected(operation, data):
    with pytest.raises(IndexError):
        operation(data, b"")


@pytest.mark.parametrize("key_length", [33, 48, 64, 65])
def test_long_keys_use_only_first_32_bytes(key_length):
    key = bytes(range(key_length))
    ciphertext = bytes.fromhex(LEGACY_VECTORS[4][2])
    plaintext = bytes((i * 17 + 128) % 256 for i in range(32))
    assert encrypt(plaintext, key) == ciphertext
    assert decrypt(ciphertext, key) == plaintext
