"""Tests for paradox.connections.serial.encryption.

The AES roundtrip itself belongs to paradox.lib.crypto and is covered by
tests/lib/test_serial_crypto.py; this module only covers key derivation.
"""

from paradox.connections.serial.encryption import make_serial_key


def test_make_serial_key_int_zero_pads_to_4_digits():
    """Integer passwords must be zero-padded to 4 digits before encoding."""
    assert make_serial_key(0)[:4] == b"0000"
    assert make_serial_key(1)[:4] == b"0001"
    assert make_serial_key(100)[:4] == b"0100"
    assert make_serial_key(1234)[:4] == b"1234"


def test_make_serial_key_string_unchanged():
    """String passwords are encoded as-is."""
    assert make_serial_key("1234")[:4] == b"1234"
    assert make_serial_key("abcd")[:4] == b"abcd"


def test_make_serial_key_always_32_bytes():
    """Key is always padded to exactly 32 bytes with 0xEE."""
    for pw in [0, 1, 1234, "1234", b"1234"]:
        key = make_serial_key(pw)
        assert len(key) == 32
        assert key[4:] == b"\xee" * 28
