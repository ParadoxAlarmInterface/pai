import binascii
from unittest.mock import Mock

import pytest

from paradox.hardware import Panel


@pytest.fixture(scope="module")
def panel_core_mock():
    return Mock()


@pytest.fixture(scope="module")
def panel(panel_core_mock):
    return Panel(panel_core_mock, None)


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
        ("", b"0000"),
    ],
)
def test_encode_password(input, expected, panel):
    enc_password = panel.encode_password(input)
    assert binascii.hexlify(enc_password) == expected

def test_build_InitiateCommunication(panel):
    payload = panel.get_message("InitiateCommunication").build({})
    assert payload == bytes.fromhex("72 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 72")

def test_parse_InitiateCommunicationResponse(panel):
    payload = bytes.fromhex('72 FF 04 02 00 00 A1 5A 01 07 70 01 05 0B 20 D4 00 10 01 00 0F 27 10 20 10 31 FF 57 45 56 4F 31 39 32 00 00 83')
    response = panel.parse_message(payload, "frompanel")
    print(response)

def test_build_StartCommunication(panel):
    payload = panel.get_message("StartCommunication").build({})
    assert payload == bytes.fromhex("5F 20 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 80")

def test_parse_StartCommunicationResponse(panel):
    payload = bytes.fromhex('00 00 00 00 05 07 70 00 00 00 00 00 08 30 02 01 00 05 0B 20 D4 04 01 01 18 40 80 38 00 00 00 00 00 00 00 00 D1')
    response = panel.parse_message(payload, "frompanel")
    print(response)