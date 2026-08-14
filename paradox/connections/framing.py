"""Transport-agnostic byte framing primitives.

Framers turn a stream of bytes into discrete frames and do nothing else.
"""

from abc import ABC, abstractmethod
import logging
from typing import Iterator, NamedTuple, Optional, Union

logger = logging.getLogger("PAI").getChild(__name__)

# Consumed bytes are reclaimed once the dead prefix passes this size. Framing
# working sets are ~115 bytes, so this keeps memmoves rare while capping the
# wasted memory per connection at 1 KB.
COMPACT_THRESHOLD = 1024

#: Fallback bound for a delimiter-framed line. Non-normative: every transport
#: should pass a limit derived from its own longest legitimate line.
DEFAULT_MAX_LINE_LENGTH = 512


class _Signal:
    """A named singleton used as a non-frame framing outcome."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return "<%s>" % self._name


#: Not enough bytes yet. Stop and wait for the next callback.
NEED_MORE = _Signal("NEED_MORE")

#: The buffer head cannot start a frame. Discard one byte and re-derive.
RESYNC = _Signal("RESYNC")


class FrameLength(NamedTuple):
    """Result of deriving a frame's length from its header."""

    length: int
    encrypted: bool = False


class Frame(NamedTuple):
    """A complete frame lifted out of the byte stream."""

    data: bytes
    encrypted: bool = False


#: What a length derivation may return.
Derivation = Union[FrameLength, _Signal]


class FrameBuffer:
    """Append-and-consume byte buffer.

    Consuming advances an integer cursor instead of rebuilding the buffer, so
    discarding a single byte to resynchronise is O(1). An immutable ``bytes``
    buffer makes that O(n), which degrades to O(n^2) across a resync storm.
    """

    __slots__ = ("_buf", "_pos")

    def __init__(self, data: bytes = b"") -> None:
        self._buf = bytearray(data)
        self._pos = 0

    def append(self, data: bytes) -> None:
        self._buf += data

    def __len__(self) -> int:
        return len(self._buf) - self._pos

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step != 1:
                raise ValueError("FrameBuffer supports contiguous slices only")
            return bytes(self._buf[self._pos + start : self._pos + stop])

        length = len(self)
        if index < 0:
            index += length
        if not 0 <= index < length:
            raise IndexError("FrameBuffer index out of range")
        return self._buf[self._pos + index]

    def peek(self, n: int) -> bytes:
        """Return up to ``n`` bytes without consuming them."""
        return bytes(self._buf[self._pos : self._pos + n])

    def find(self, sub: bytes, start: int = 0) -> int:
        """Return the index of ``sub`` within the pending bytes, or ``-1``.

        Searching the underlying buffer from the cursor avoids materialising a
        copy of the pending bytes. Doing that once per frame is what turns a
        burst of buffered lines into O(n^2) work.
        """
        index = self._buf.find(sub, self._pos + start)
        return -1 if index < 0 else index - self._pos

    def take(self, n: int) -> bytes:
        """Consume and return up to ``n`` bytes."""
        chunk = self.peek(n)
        self._pos += len(chunk)
        return chunk

    def discard(self, n: int = 1) -> bytes:
        """Consume ``n`` bytes and return them, for logging."""
        return self.take(n)

    def clear(self) -> None:
        self._buf = bytearray()
        self._pos = 0

    def compact(self) -> None:
        """Reclaim the consumed prefix. Cheap to call after every feed."""
        if self._pos == 0:
            return
        if self._pos >= len(self._buf):
            self.clear()
        elif self._pos >= COMPACT_THRESHOLD:
            del self._buf[: self._pos]
            self._pos = 0

    @property
    def pending(self) -> bytes:
        """The unconsumed bytes, for debugging and assertions."""
        return bytes(self._buf[self._pos :])

    def __repr__(self) -> str:
        return "FrameBuffer(%d pending)" % len(self)


class Framer(ABC):
    """Shared feed-and-extract loop for every transport's framer.

    Subclasses implement :meth:`_next_frame` and nothing else: it returns the
    next :class:`Frame`, or ``None`` when the buffer cannot yield one yet.
    Consuming and resynchronising are the subclass's business; this class only
    guarantees how the bytes get in and how frames come out.
    """

    def __init__(self) -> None:
        self.buffer = FrameBuffer()

    def reset(self) -> None:
        """Drop any partially received frame."""
        self.buffer.clear()

    def feed(self, data: bytes) -> Iterator[Frame]:
        """Append ``data`` and yield every frame it completes.

        The append is eager, so bytes are never lost if the caller drops the
        iterator without consuming it. Only extraction is deferred: yielding
        lazily means that if the consumer raises while handling frame *n*,
        frames *n+1..* stay buffered and are re-parsed on the next feed
        instead of being silently dropped.
        """
        self.buffer.append(data)
        return self._iter_frames()

    def _iter_frames(self) -> Iterator[Frame]:
        try:
            while True:
                frame = self._next_frame()
                if frame is None:
                    return
                yield frame
        finally:
            self.buffer.compact()

    @abstractmethod
    def _next_frame(self) -> Optional[Frame]:
        """Return the next frame, or ``None`` to wait for more data."""
        raise NotImplementedError


class LineFramer(Framer):
    """Splits a byte stream on a terminator.

    Line-oriented transports differ in what they want out of a line, so the
    policy is the caller's to set:

    ``strip_terminator``
        Drop the terminator from the emitted frame. Off by default, so the
        consumer can verify framing.
    ``drop_blank_lines``
        Skip lines whose payload has no printable content. Off by default,
        which skips only genuinely empty payloads: a bare terminator carries
        no message, but a whitespace-only line may still be data.

    ``max_line_length``
        Discard the buffer once it exceeds this without a terminator. The
        default is a fallback only: a bound that suits one transport's line
        lengths silently truncates another's, so pass your own.
    """

    def __init__(
        self,
        terminator: bytes = b"\r",
        max_line_length: int = DEFAULT_MAX_LINE_LENGTH,
        strip_terminator: bool = False,
        drop_blank_lines: bool = False,
    ) -> None:
        super().__init__()
        if not terminator:
            raise ValueError("terminator must be at least one byte")
        self._terminator = terminator
        self._max_line_length = max_line_length
        self._strip_terminator = strip_terminator
        self._drop_blank_lines = drop_blank_lines

    def _next_frame(self) -> Optional[Frame]:
        """Return the next line, or ``None`` to wait for more data."""
        while True:
            index = self.buffer.find(self._terminator)
            if index < 0:
                # Only now, with no complete line left to rescue, is a large
                # buffer evidence of a lost terminator rather than of a burst
                # of good lines still waiting to be extracted.
                if len(self.buffer) > self._max_line_length:
                    logger.warning(
                        "Line buffer overflow (%d bytes > %d), discarding",
                        len(self.buffer),
                        self._max_line_length,
                    )
                    self.buffer.clear()
                return None

            line = self.buffer.take(index + len(self._terminator))
            payload = line[: -len(self._terminator)]
            if self._drop_blank_lines:
                if not payload.strip():
                    continue
            elif not payload:
                continue

            return Frame(payload if self._strip_terminator else line)


def checksum(data: bytes) -> bool:
    """True when the last byte equals the 8-bit sum of the preceding bytes."""
    if not data:
        return False
    return sum(data[:-1]) % 256 == data[-1]
