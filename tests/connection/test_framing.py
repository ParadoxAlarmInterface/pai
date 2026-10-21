"""Tests for paradox.connections.framing — transport-agnostic framing primitives."""

import pytest

from paradox.connections.framing import (
    COMPACT_THRESHOLD,
    NEED_MORE,
    RESYNC,
    Frame,
    FrameBuffer,
    FrameLength,
    Framer,
    checksum,
)


def test_append_and_len():
    buf = FrameBuffer()
    buf.append(b"abc")
    buf.append(b"de")
    assert len(buf) == 5


def test_peek_does_not_consume():
    buf = FrameBuffer(b"abcde")
    assert buf.peek(3) == b"abc"
    assert len(buf) == 5
    assert buf.pending == b"abcde"


def test_take_consumes():
    buf = FrameBuffer(b"abcde")
    assert buf.take(3) == b"abc"
    assert len(buf) == 2
    assert buf.pending == b"de"


def test_take_more_than_available_returns_what_there_is():
    buf = FrameBuffer(b"ab")
    assert buf.take(10) == b"ab"
    assert len(buf) == 0


def test_find_returns_index_relative_to_the_pending_bytes():
    buf = FrameBuffer(b"abcXdefX")
    buf.take(4)
    assert buf.find(b"X") == 3


def test_find_returns_minus_one_when_absent():
    buf = FrameBuffer(b"abc")
    assert buf.find(b"X") == -1


def test_find_ignores_consumed_bytes():
    buf = FrameBuffer(b"X abc")
    buf.take(1)
    assert buf.find(b"X") == -1


def test_find_honours_the_start_offset():
    buf = FrameBuffer(b"aXbX")
    assert buf.find(b"X", 2) == 3


def test_find_does_not_consume():
    buf = FrameBuffer(b"abX")
    buf.find(b"X")
    assert buf.pending == b"abX"


def test_discard_defaults_to_one_byte_and_returns_it():
    buf = FrameBuffer(b"abc")
    assert buf.discard() == b"a"
    assert buf.pending == b"bc"


def test_discard_on_empty_buffer_returns_empty():
    buf = FrameBuffer()
    assert buf.discard() == b""


def test_indexing_is_relative_to_cursor():
    buf = FrameBuffer(b"abcde")
    buf.take(2)
    assert buf[0] == ord("c")
    assert buf[1] == ord("d")
    assert buf[-1] == ord("e")


def test_index_out_of_range_raises():
    buf = FrameBuffer(b"ab")
    with pytest.raises(IndexError):
        buf[2]


def test_slicing_is_relative_to_cursor():
    buf = FrameBuffer(b"abcde")
    buf.take(1)
    assert buf[:2] == b"bc"
    assert buf[1:3] == b"cd"


def test_slice_with_step_is_rejected():
    buf = FrameBuffer(b"abcde")
    with pytest.raises(ValueError):
        buf[::2]


def test_clear_empties_buffer():
    buf = FrameBuffer(b"abc")
    buf.clear()
    assert len(buf) == 0
    assert buf.pending == b""


def test_compact_resets_when_fully_drained():
    buf = FrameBuffer(b"abc")
    buf.take(3)
    buf.compact()
    assert buf.pending == b""
    assert len(buf) == 0


def test_compact_below_threshold_preserves_content():
    buf = FrameBuffer(b"abcde")
    buf.take(2)
    buf.compact()
    assert buf.pending == b"cde"


def test_compact_above_threshold_reclaims_memory():
    buf = FrameBuffer(b"x" * (COMPACT_THRESHOLD + 10))
    buf.take(COMPACT_THRESHOLD + 5)
    buf.compact()
    assert buf.pending == b"xxxxx"


def test_repeated_single_byte_discards_stay_correct():
    buf = FrameBuffer(b"0123456789")
    for _ in range(5):
        buf.discard()
    assert buf.pending == b"56789"


def test_checksum_valid():
    assert checksum(b"\x01\x02\x03") is True


def test_checksum_invalid():
    assert checksum(b"\x01\x02\x04") is False


def test_checksum_wraps_at_256():
    assert checksum(b"\xff\xff\xfe") is True


def test_checksum_on_empty_is_false():
    assert checksum(b"") is False


def test_signals_are_distinct_and_have_readable_repr():
    assert NEED_MORE is not RESYNC
    assert "NEED_MORE" in repr(NEED_MORE)
    assert "RESYNC" in repr(RESYNC)


def test_frame_length_defaults_to_unencrypted():
    assert FrameLength(37).encrypted is False
    assert FrameLength(37).length == 37


def test_frame_defaults_to_unencrypted():
    assert Frame(b"abc").encrypted is False
    assert Frame(b"abc").data == b"abc"


# feed() defers frame extraction but must not defer the append: a caller that
# drops the iterator without consuming it would otherwise lose the bytes.


@pytest.mark.parametrize(
    "make_framer, data",
    [
        (lambda: _serial_framer(), b"\x12\x06"),
        (lambda: _ip_framer(), b"\xaa\x05\x00" + b"\x00" * 13 + b"hello"),
        (lambda: _line_framer(), b"AT\r"),
    ],
    ids=["serial", "ip", "prt3"],
)
def test_feed_buffers_data_even_if_iterator_is_never_consumed(make_framer, data):
    framer = make_framer()

    framer.feed(data)  # deliberately not iterated

    assert framer.buffer.pending == data


def _serial_framer():
    from paradox.connections.serial.framing import SerialFramer

    return SerialFramer()


def _ip_framer():
    from paradox.connections.ip.framing import IPFramer

    return IPFramer()


def _line_framer():
    from paradox.connections.framing import LineFramer

    return LineFramer()


class TestFramerContract:
    """All three transports share one feed/extract loop."""

    def test_every_framer_implements_the_shared_contract(self):
        for make in (_serial_framer, _ip_framer, _line_framer):
            framer = make()
            assert isinstance(framer, Framer)
            assert framer.buffer.pending == b""

    def test_next_frame_is_required(self):
        class Incomplete(Framer):
            pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_reset_drops_a_partial_frame(self):
        for make, partial in (
            (_serial_framer, b"\x12"),
            (_ip_framer, b"\xaa\x05"),
            (_line_framer, b"AT"),
        ):
            framer = make()
            list(framer.feed(partial))
            assert framer.buffer.pending == partial
            framer.reset()
            assert framer.buffer.pending == b""
