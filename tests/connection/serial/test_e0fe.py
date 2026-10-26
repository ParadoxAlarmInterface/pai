"""Tests for the ``E0 FE`` serial codec.

Messages are synthetic (invented panel fields). Expected frames were produced
by an independent implementation of the wrapping, not by the code under test.
"""

import pytest

from paradox.connections.serial import framing as serial_framing
from paradox.connections.serial.e0fe import (
    FRAME_OVERHEAD,
    MAX_FRAME_LENGTH,
    MIN_FRAME_LENGTH,
    E0FECodec,
    _cipher,
    is_frame,
)

# Identify echo sent by the PC: 72 FF, invented serial/product fields, "TESTPANEL1".
IDENTIFY_ECHO = bytes.fromhex(
    "72ff0102030405a5112233441357acde0001020304050607" "5445535450414e454c3100ba7a"
)
# The panel's identify reply: same fields, last two payload bytes zero.
IDENTIFY_REPLY = bytes.fromhex(
    "72ff0102030405a5112233441357acde0001020304050607" "5445535450414e454c310000c0"
)
# StartCommunication request: 5F 20, zeros, checksum.
START_COMMUNICATION = bytes.fromhex("5f20" + "00" * 34 + "7f")
# An arbitrary 37-byte reply with a valid checksum.
REPLY = bytes.fromhex("0011" + bytes(range(0x20, 0x42)).hex() + "82")

# IDENTIFY_ECHO wrapped from the initial state (seq 00, seed 00): q prefix, XORed.
TX_IDENTIFY = bytes.fromhex(
    "e0fe2e00002febde21b3d113a1b780d13542a52df361ca89ed39802caa3ec722"
    "5a81bbb11b0956c7642cf4000415"
)
# IDENTIFY_REPLY from the panel: q prefix without the XOR, seq 00, seed 5a.
RX_IDENTIFY = bytes.fromhex(
    "e0fe2e0000b41291a34f798c5c85fc81d0395dad7c0c16f2044df5257774a4ea"
    "ae7c88d6560b85272b8af35ad614"
)
# START_COMMUNICATION wrapped after RX_IDENTIFY: p prefix, seq 00, seed 5a.
TX_START_COMMUNICATION = bytes.fromhex(
    "e0fe2e000034812ee34e2988dd57dd959bb8470abf9316fa445ff4376326607b"
    "b55facf46587247f2b8a0e5a0f14"
)
# REPLY from the panel: p prefix, seq 01, seed 3c.
RX_REPLY = bytes.fromhex(
    "e0fe2e000172d45dbc96360ae5c460dec5c619e1098121971ff282b14903e38d"
    "a2c23307d9c40701648b663cc414"
)
# START_COMMUNICATION wrapped after RX_REPLY: p prefix, seq 01, seed 3c.
TX_AFTER_REPLY = bytes.fromhex(
    "e0fe2e0001720941fc06be6ee34e2988dd57dd959bb8470abf9316fa445ff437"
    "6326607bb55facf46587d93c6c15"
)
# The shortest frame: one-byte message 00, p prefix, seq 07, seed 99.
RX_MINIMAL = bytes.fromhex("e0fe0a0007b5cc990904")


def corrupt(frame, index):
    data = bytearray(frame)
    data[index] ^= 0x01
    return bytes(data)


def with_outer_checksum(frame):
    """Recompute the 16-bit checksum so only an inner field is wrong."""
    body = frame[:-2]
    return body + (sum(body) & 0xFFFF).to_bytes(2, "little")


@pytest.fixture
def codec():
    return E0FECodec()


def state(codec):
    return codec.seq, codec.seed


def test_initial_state(codec):
    assert state(codec) == (0, 0)


def test_exchange(codec):
    assert codec.wrap(IDENTIFY_ECHO) == TX_IDENTIFY
    assert state(codec) == (1, 0x00)
    assert codec.unwrap(RX_IDENTIFY) == IDENTIFY_REPLY
    assert state(codec) == (0, 0x5A)
    assert codec.wrap(START_COMMUNICATION) == TX_START_COMMUNICATION
    assert state(codec) == (1, 0x5A)
    assert codec.unwrap(RX_REPLY) == REPLY
    assert state(codec) == (1, 0x3C)
    assert codec.wrap(START_COMMUNICATION) == TX_AFTER_REPLY
    assert state(codec) == (2, 0x3C)


def decrypt_body(frame):
    return _cipher(frame[5:-3], frame[4], frame[-3], decrypt=True)


def test_q_prefix_xor_on_transmit():
    # Bytes 12-15 of the identify message give the XOR key for all of it.
    key = 0x13 ^ 0x57 ^ 0xAC ^ 0xDE
    expected = b"\x71" + bytes(b ^ key for b in IDENTIFY_ECHO)
    assert decrypt_body(E0FECodec().wrap(IDENTIFY_ECHO)) == expected


def test_q_prefix_received_without_xor(codec):
    assert decrypt_body(RX_IDENTIFY) == b"\x71" + IDENTIFY_REPLY
    assert codec.unwrap(RX_IDENTIFY) == IDENTIFY_REPLY


def test_minimal_frame(codec):
    assert len(RX_MINIMAL) == MIN_FRAME_LENGTH
    assert codec.unwrap(RX_MINIMAL) == b"\x00"
    assert state(codec) == (0x07, 0x99)


def test_independent_instances():
    a, b = E0FECodec(), E0FECodec()
    a.unwrap(RX_REPLY)
    assert state(a) == (1, 0x3C)
    assert state(b) == (0, 0)
    assert b.wrap(IDENTIFY_ECHO) == TX_IDENTIFY


@pytest.mark.parametrize(
    "message",
    [b"\x00", START_COMMUNICATION, REPLY, bytes(70) + b"\x00"],
    ids=["one-byte", "start-communication", "reply", "longest"],
)
def test_round_trip(message):
    tx, rx = E0FECodec(), E0FECodec()
    for _ in range(3):
        frame = tx.wrap(message)
        assert is_frame(frame)
        assert rx.unwrap(frame) == message
        assert state(rx) == (frame[4], frame[-3])


def test_longest_message_fits_bound():
    assert MAX_FRAME_LENGTH == FRAME_OVERHEAD + 1 + serial_framing.MAX_MESSAGE_LENGTH
    frame = E0FECodec().wrap(bytes(serial_framing.MAX_MESSAGE_LENGTH))
    assert len(frame) == MAX_FRAME_LENGTH


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        RX_REPLY[: MIN_FRAME_LENGTH - 1],
        RX_REPLY[:-1],
        RX_REPLY + b"\x00",
        b"\xe1" + RX_REPLY[1:],
        corrupt(RX_REPLY, -1),
        corrupt(RX_REPLY, 2),
        with_outer_checksum(corrupt(RX_REPLY, 10)),
        with_outer_checksum(corrupt(RX_REPLY, 5)),
    ],
    ids=[
        "empty",
        "too-short",
        "truncated",
        "trailing-byte",
        "bad-header",
        "bad-outer-checksum",
        "bad-length",
        "bad-inner-checksum",
        "bad-prefix",
    ],
)
def test_invalid_frame_leaves_state(codec, frame):
    codec.unwrap(RX_IDENTIFY)
    with pytest.raises(ValueError):
        codec.unwrap(frame)
    assert state(codec) == (0, 0x5A)


def test_oversize_frame_rejected(codec):
    length = MAX_FRAME_LENGTH + 1
    frame = b"\xe0\xfe" + length.to_bytes(2, "little") + bytes(length - 6)
    frame += (sum(frame) & 0xFFFF).to_bytes(2, "little")
    assert not is_frame(frame)
    with pytest.raises(ValueError):
        codec.unwrap(frame)


@pytest.mark.parametrize(
    "message",
    [b"", b"\x01", START_COMMUNICATION[:-1] + b"\x00", bytes(72), b"\x72\xff\x71"],
    ids=["empty", "bad-checksum", "bad-checksum-37", "too-long", "short-identify"],
)
def test_invalid_message_leaves_state(codec, message):
    with pytest.raises(ValueError):
        codec.wrap(message)
    assert state(codec) == (0, 0)
