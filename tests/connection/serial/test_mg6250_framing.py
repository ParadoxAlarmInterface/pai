"""Tests for the MG6250 framer.

Header layout per BabyWare's encoder/decoder: ``DE | cmd LE16 | LEN LE16 |
lenA | lenB``
"""

import pytest

from paradox.connections.serial.mg6250_framing import (
    MAX_MESSAGE_LENGTH,
    MG6250SerialFramer,
    crc16_modbus,
)

# PC identify request and the panel's second identify reply, as captured.
IDENTIFY = bytes.fromhex("de00000a00000001951a")
IDENTIFY_REPLY_2 = bytes.fromhex(
    "de00002e0000000200000100020005000700080009000a000f00170018001900"
    "1a00200021002200230024007129"
)


def make_frame(command, body):
    length = 7 + len(body) + 2
    head = bytes([0xDE]) + command.to_bytes(2, "little") + length.to_bytes(2, "little")
    data = head + b"\x00\x00" + body
    return data + crc16_modbus(data)


def frames(framer, data):
    return [f.data for f in framer.feed(data)]


@pytest.fixture
def framer():
    return MG6250SerialFramer()


def test_captured_frames(framer):
    assert frames(framer, IDENTIFY + IDENTIFY_REPLY_2) == [IDENTIFY, IDENTIFY_REPLY_2]


def test_byte_by_byte(framer):
    out = []
    for b in IDENTIFY_REPLY_2:
        out += frames(framer, bytes([b]))
    assert out == [IDENTIFY_REPLY_2]


def test_length_is_16_bit_little_endian(framer):
    big = make_frame(0x24, bytes(range(256)) * 2)
    assert len(big) > 0xFF and big[4] != 0
    assert frames(framer, big) == [big]


def test_resync_past_junk_and_false_sof(framer):
    # 0xDE with a valid-looking length but a bad CRC must cost one byte only.
    junk = b"\x11\xde\x00\x00\x0a\x00\x00\x00\x01\x00\x00"
    assert frames(framer, junk + IDENTIFY) == [IDENTIFY]


def test_implausible_length_resyncs(framer):
    too_long = (MAX_MESSAGE_LENGTH + 1).to_bytes(2, "little")
    head = b"\xde\x24\x00" + too_long
    assert frames(framer, head + IDENTIFY) == [IDENTIFY]


def test_waits_for_whole_frame(framer):
    assert frames(framer, IDENTIFY_REPLY_2[:-1]) == []
    assert frames(framer, IDENTIFY_REPLY_2[-1:]) == [IDENTIFY_REPLY_2]
