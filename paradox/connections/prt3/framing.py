"""Framing for the PRT3 ASCII line protocol.

Pure byte handling: no asyncio, no transport.
"""

import logging
from typing import Iterator

from paradox.connections.framing import Frame, FrameBuffer

logger = logging.getLogger("PAI").getChild(__name__)

#: PRT3 lines are ~21 bytes; anything much larger means the delimiter was lost.
MAX_LINE_LENGTH = 512


class LineFramer:
    """Splits a byte stream on a terminator, keeping the terminator."""

    def __init__(
        self, terminator: bytes = b"\r", max_line_length: int = MAX_LINE_LENGTH
    ) -> None:
        self.buffer = FrameBuffer()
        self._terminator = terminator
        self._max_line_length = max_line_length

    def reset(self) -> None:
        self.buffer.clear()

    def feed(self, data: bytes) -> Iterator[Frame]:
        """Append ``data`` and yield each complete line, terminator included.

        Lines with no printable content are dropped: a bare terminator carries
        no message.
        """
        self.buffer.append(data)

        if len(self.buffer) > self._max_line_length:
            logger.warning(
                "PRT3: buffer overflow (%d bytes), discarding", len(self.buffer)
            )
            self.buffer.clear()
            return

        try:
            while True:
                pending = self.buffer.pending
                index = pending.find(self._terminator)
                if index < 0:
                    return

                line = self.buffer.take(index + len(self._terminator))
                if line[: -len(self._terminator)].strip():
                    yield Frame(line)
        finally:
            self.buffer.compact()
