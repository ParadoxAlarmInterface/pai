"""Tests for the IP150 framer."""

import pytest

from paradox.connections.framing import NEED_MORE, RESYNC
from paradox.connections.ip.framing import IP_HEADER_LENGTH, MAX_IP_PAYLOAD, IPFramer


def header(length, encrypted=True):
    """A 16 byte IP150 header with the given little-endian payload length."""
    flags = 0x09 if encrypted else 0x08
    return (
        bytes([0xAA, length & 0xFF, (length >> 8) & 0xFF, 0x02, flags]) + b"\xee" * 11
    )


def message(payload, encrypted=True):
    body = payload
    pad = (-len(payload)) % 16
    body = payload + b"\xee" * pad
    return header(len(payload), encrypted) + body


@pytest.fixture
def framer():
    return IPFramer()


def frames(framer, data):
    return list(framer.feed(data))


class TestEmptyAndPartial:
    def test_empty_data_does_not_raise(self, framer):
        # Regression: indexing an empty buffer used to raise IndexError.
        assert frames(framer, b"") == []

    def test_partial_header_waits(self, framer):
        assert frames(framer, b"\xaa\x06\x00") == []

    def test_partial_payload_waits(self, framer):
        msg = message(b"\x01" * 20)
        assert frames(framer, msg[:-5]) == []
        assert len(frames(framer, msg[-5:])) == 1


class TestLengthDerivation:
    def test_length_is_little_endian_16_bit(self, framer):
        # Regression: only the low byte used to be read, so any payload of
        # 256 bytes or more was mis-framed.
        assert framer.derive_length(header(300)).length == IP_HEADER_LENGTH + 304

    def test_encrypted_payload_is_padded_to_16(self, framer):
        assert framer.derive_length(header(6)).length == IP_HEADER_LENGTH + 16

    def test_unencrypted_payload_is_also_padded(self, framer):
        # The wire pads regardless of the encrypt flag: the original
        # implementation only ever processed 16-aligned totals. Taking just
        # `length` bytes would strand the padding and drop the next message.
        assert framer.derive_length(header(6, encrypted=False)).length == (
            IP_HEADER_LENGTH + 16
        )

    def test_zero_length_payload_is_header_only(self, framer):
        assert framer.derive_length(header(0)).length == IP_HEADER_LENGTH

    def test_short_header_needs_more(self, framer):
        assert framer.derive_length(b"\xaa\x06") is NEED_MORE

    def test_bad_sof_resyncs(self, framer):
        assert framer.derive_length(b"\xbb" + b"\x00" * 15) is RESYNC

    def test_oversized_payload_resyncs(self, framer):
        assert framer.derive_length(header(MAX_IP_PAYLOAD + 1)) is RESYNC


class TestFraming:
    def test_single_message_emits(self, framer):
        msg = message(b"\x01" * 6)
        assert [f.data for f in frames(framer, msg)] == [msg]

    def test_unencrypted_message_emits(self, framer):
        msg = message(b"\x01" * 6, encrypted=False)
        assert [f.data for f in frames(framer, msg)] == [msg]

    def test_pipelined_unencrypted_messages_all_emit(self, framer):
        # Regression: taking only `length` bytes for an unencrypted message
        # left its padding in the buffer, which failed the SOF check and made
        # _drop_buffer() discard every message queued behind it.
        a = message(b"\x01" * 6, encrypted=False)
        b = message(b"\x02" * 6, encrypted=False)
        assert [f.data for f in frames(framer, a + b)] == [a, b]

    def test_pipelined_messages_all_emit(self, framer):
        # Regression: only the first message used to be processed and the rest
        # of the buffer was thrown away.
        a = message(b"\x01" * 6)
        b = message(b"\x02" * 20)
        assert [f.data for f in frames(framer, a + b)] == [a, b]

    def test_byte_at_a_time_delivery_reassembles(self, framer):
        msg = message(b"\x01" * 6)
        out = []
        for i in range(len(msg)):
            out += frames(framer, msg[i : i + 1])
        assert [f.data for f in out] == [msg]

    def test_message_split_across_callbacks_reassembles(self, framer):
        msg = message(b"\x01" * 40)
        assert frames(framer, msg[:20]) == []
        assert [f.data for f in frames(framer, msg[20:])] == [msg]


class TestDesync:
    def test_garbage_clears_the_buffer(self, framer):
        # This is TCP: a corrupt stream cannot be resynchronised by sliding,
        # so the framer drops everything and waits for the next message.
        assert frames(framer, b"\xbb" * 40) == []
        assert len(framer.buffer) == 0

    def test_message_after_garbage_is_framed(self, framer):
        frames(framer, b"\xbb" * 40)
        msg = message(b"\x01" * 6)
        assert [f.data for f in frames(framer, msg)] == [msg]

    def test_oversized_length_clears_rather_than_buffering(self, framer):
        frames(framer, header(MAX_IP_PAYLOAD + 100))
        assert len(framer.buffer) == 0


class TestReset:
    def test_reset_drops_buffered_bytes(self, framer):
        frames(framer, b"\xaa\x06\x00")
        assert len(framer.buffer) == 3
        framer.reset()
        assert len(framer.buffer) == 0
