"""Tests for the PRT3 line framer."""

import pytest

from paradox.connections.framing import Frame
from paradox.connections.prt3.framing import MAX_LINE_LENGTH, LineFramer


@pytest.fixture
def framer():
    return LineFramer()


def lines(framer, data):
    return [f.data for f in framer.feed(data)]


def test_complete_line_is_emitted_with_terminator(framer):
    assert lines(framer, b"G001N001\r") == [b"G001N001\r"]


def test_partial_line_is_not_emitted(framer):
    assert lines(framer, b"G001N001") == []
    assert framer.buffer.pending == b"G001N001"


def test_line_split_across_feeds_reassembles(framer):
    assert lines(framer, b"G001") == []
    assert lines(framer, b"N001\r") == [b"G001N001\r"]


def test_two_lines_in_one_feed_both_emit(framer):
    assert lines(framer, b"A\rB\r") == [b"A\r", b"B\r"]


def test_remainder_after_a_line_is_kept(framer):
    assert lines(framer, b"A\rBC") == [b"A\r"]
    assert framer.buffer.pending == b"BC"


def test_bare_terminator_is_discarded(framer):
    assert lines(framer, b"\r") == []


def test_whitespace_only_line_is_discarded(framer):
    assert lines(framer, b"   \r") == []


def test_empty_line_between_real_lines_is_skipped(framer):
    assert lines(framer, b"A\r\rB\r") == [b"A\r", b"B\r"]


def test_buffer_is_drained_after_a_complete_line(framer):
    lines(framer, b"A\r")
    assert framer.buffer.pending == b""


def test_overflow_discards_the_buffer(framer):
    assert lines(framer, b"x" * (MAX_LINE_LENGTH + 1)) == []
    assert framer.buffer.pending == b""


def test_recovers_after_overflow(framer):
    lines(framer, b"x" * (MAX_LINE_LENGTH + 1))
    assert lines(framer, b"A\r") == [b"A\r"]


def test_reset_drops_buffered_bytes(framer):
    lines(framer, b"AB")
    framer.reset()
    assert framer.buffer.pending == b""


def test_emitted_value_is_a_frame(framer):
    assert list(framer.feed(b"A\r")) == [Frame(b"A\r")]


def test_custom_terminator():
    framer = LineFramer(terminator=b"\n")
    assert [f.data for f in framer.feed(b"A\nB\n")] == [b"A\n", b"B\n"]
