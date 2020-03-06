import binascii

import pytest
from paradox.hardware import Panel


@pytest.mark.parametrize(
    "input,expected",
    [
        (b"1234", b"1234"),
        (b"0000", b"0000"),
        (b"0001", b"0001"),
        (b"1000", b"1000"),
        ("1234", b"1234"),
        ("0000", b"0000"),
        ("0001", b"0001"),
        ("1000", b"1000"),
        (1234, b"1234"),
        (0000, b"0000"),
        (1, b"0001"),
        (1000, b"1000"),
        (b"0bcd", b"0bcd"),
        (None, b"0000"),
    ],
)
def test_encode_password(input, expected, mocker):
    panel = Panel(mocker.MagicMock(), None, None)

    enc_password = panel.encode_password(input)
    assert binascii.hexlify(enc_password) == expected
