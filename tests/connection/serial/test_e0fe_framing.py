"""Tests for the ``E0 FE`` serial framer."""

import pytest

from paradox.connections.serial.e0fe import MAX_FRAME_LENGTH, E0FECodec
from paradox.connections.serial.e0fe_framing import E0FESerialFramer

from tests.connection.serial.test_e0fe import (
    IDENTIFY_REPLY,
    REPLY,
    RX_IDENTIFY,
    RX_MINIMAL,
    RX_REPLY,
    corrupt,
)

STREAM = IDENTIFY_REPLY + RX_IDENTIFY + RX_MINIMAL + RX_REPLY
EXPECTED = [
    (IDENTIFY_REPLY, False),
    (RX_IDENTIFY, True),
    (RX_MINIMAL, True),
    (RX_REPLY, True),
]


def frames(framer, data):
    return [(f.data, f.encrypted) for f in framer.feed(data)]


@pytest.fixture
def framer():
    return E0FESerialFramer()


def test_coalesced(framer):
    assert frames(framer, STREAM) == EXPECTED
    assert len(framer.buffer) == 0


def test_byte_by_byte(framer):
    out = []
    for b in STREAM:
        out += frames(framer, bytes([b]))
    assert out == EXPECTED


def test_every_split_point():
    for split in range(len(STREAM) + 1):
        framer = E0FESerialFramer()
        out = frames(framer, STREAM[:split]) + frames(framer, STREAM[split:])
        assert out == EXPECTED, split


def test_frames_unwrap(framer):
    codec = E0FECodec()
    out = [codec.unwrap(f) for f, encrypted in frames(framer, STREAM) if encrypted]
    assert out == [IDENTIFY_REPLY, b"\x00", REPLY]


def test_junk_before_frames(framer):
    junk = b"\x00\x11\x72\x00\xe0\x00\xe0\xfe"
    assert frames(framer, junk + STREAM) == EXPECTED


@pytest.mark.parametrize(
    "length",
    [0, 1, 9, MAX_FRAME_LENGTH + 1, 0xFFFF],
)
def test_implausible_length_resyncs(framer, length):
    head = b"\xe0\xfe" + length.to_bytes(2, "little")
    assert frames(framer, head + RX_REPLY) == [(RX_REPLY, True)]


def test_bad_outer_checksum_costs_one_byte(framer):
    assert frames(framer, corrupt(RX_REPLY, -1) + RX_REPLY) == [(RX_REPLY, True)]


def test_bad_length_field_costs_one_byte(framer):
    # A length one short of the real frame cannot checksum.
    bad = RX_REPLY[:2] + bytes([RX_REPLY[2] - 1]) + RX_REPLY[3:]
    assert frames(framer, bad + RX_REPLY) == [(RX_REPLY, True)]


def test_bad_identify_checksum_costs_one_byte(framer):
    assert frames(framer, corrupt(IDENTIFY_REPLY, -1) + RX_REPLY) == [(RX_REPLY, True)]


def test_waits_for_whole_frame(framer):
    assert frames(framer, RX_REPLY[:-1]) == []
    assert frames(framer, RX_REPLY[-1:]) == [(RX_REPLY, True)]


def test_false_header_wait_is_bounded(framer):
    # A false header claiming the longest frame holds at most that many bytes.
    head = b"\xe0\xfe" + MAX_FRAME_LENGTH.to_bytes(2, "little")
    stream = head + RX_REPLY + RX_REPLY
    assert len(stream) >= MAX_FRAME_LENGTH
    assert frames(framer, stream) == [(RX_REPLY, True), (RX_REPLY, True)]


def test_junk_never_accumulates(framer):
    assert frames(framer, bytes(range(256)) * 20) == []
    assert len(framer.buffer) < MAX_FRAME_LENGTH
    assert frames(framer, RX_REPLY) == [(RX_REPLY, True)]


def test_plain_messages_are_not_frames(framer):
    # Outside the identify reply, unwrapped messages never appear on the link.
    plain = bytes.fromhex("120600000018")
    assert frames(framer, plain + RX_REPLY) == [(RX_REPLY, True)]


def test_reset(framer):
    assert frames(framer, RX_REPLY[:10]) == []
    framer.reset()
    assert frames(framer, RX_REPLY) == [(RX_REPLY, True)]
