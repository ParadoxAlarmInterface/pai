"""Tests for the shared line framer."""

import pytest

from paradox.connections.framing import DEFAULT_MAX_LINE_LENGTH, Frame, LineFramer

MAX_LINE_LENGTH = DEFAULT_MAX_LINE_LENGTH


@pytest.fixture
def framer():
    """A framer configured the way PRT3 uses it."""
    return LineFramer(
        terminator=b"\r", max_line_length=MAX_LINE_LENGTH, drop_blank_lines=True
    )


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


def test_empty_terminator_is_rejected():
    with pytest.raises(ValueError):
        LineFramer(terminator=b"")


def test_multi_byte_terminator():
    framer = LineFramer(terminator=b"\r\n")
    assert [f.data for f in framer.feed(b"A\r\nB\r\n")] == [b"A\r\n", b"B\r\n"]


def test_strip_terminator_drops_the_delimiter():
    framer = LineFramer(terminator=b"\r\n", strip_terminator=True)
    assert [f.data for f in framer.feed(b"A\r\nB\r\n")] == [b"A", b"B"]


def test_whitespace_only_line_survives_by_default():
    """Only a genuinely empty payload is skipped when blanks are kept.

    A whitespace-only line may still be data -- an SMS body of a single
    space, for instance -- so dropping it is opt-in.
    """
    framer = LineFramer(terminator=b"\r\n", strip_terminator=True)
    assert [f.data for f in framer.feed(b"\r\n \r\n")] == [b" "]


def test_max_line_length_is_per_caller():
    framer = LineFramer(terminator=b"\r", max_line_length=8)
    assert [f.data for f in framer.feed(b"x" * 9)] == []
    assert framer.buffer.pending == b""


def test_burst_of_complete_lines_over_the_cap_is_not_discarded(framer):
    """The cap targets a lost terminator, not a backlog of good lines.

    The overflow check used to run before extraction, so a burst larger than
    MAX_LINE_LENGTH threw away every complete line it contained.
    """
    burst = b"".join(b"G001N%03d\r" % i for i in range(60))
    assert len(burst) > MAX_LINE_LENGTH

    assert len(list(framer.feed(burst))) == 60
    assert framer.buffer.pending == b""


def test_oversized_run_without_terminator_is_still_discarded(framer):
    list(framer.feed(b"X" * (MAX_LINE_LENGTH + 1)))
    assert framer.buffer.pending == b""
