"""Transport-agnostic byte framing primitives.

Nothing here imports asyncio or touches a transport. Framers turn a stream of
bytes into discrete frames and do nothing else, which is what makes framing
directly unit-testable with plain ``bytes`` and no mocks.
"""

import logging
from typing import NamedTuple, Union

logger = logging.getLogger("PAI").getChild(__name__)

# Consumed bytes are reclaimed once the dead prefix passes this size. Framing
# working sets are ~115 bytes, so this keeps memmoves rare while capping the
# wasted memory per connection at 1 KB.
COMPACT_THRESHOLD = 1024


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


def checksum(data: bytes) -> bool:
    """True when the last byte equals the 8-bit sum of the preceding bytes."""
    if not data:
        return False
    return sum(data[:-1]) % 256 == data[-1]
