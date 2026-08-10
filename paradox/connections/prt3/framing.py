"""Framing for the PRT3 ASCII line protocol.

Pure byte handling: no asyncio, no transport.
"""

import logging

from paradox.connections.framing import Frame, Framer

logger = logging.getLogger("PAI").getChild(__name__)

#: PRT3 lines are ~21 bytes; anything much larger means the delimiter was lost.
MAX_LINE_LENGTH = 512


class LineFramer(Framer):
    """Splits a byte stream on a terminator, keeping the terminator."""

    def __init__(
        self, terminator: bytes = b"\r", max_line_length: int = MAX_LINE_LENGTH
    ) -> None:
        super().__init__()
        self._terminator = terminator
        self._max_line_length = max_line_length

    def _next_frame(self):
        """Return the next non-empty line, or ``None`` to wait for more data.

        Lines with no printable content are skipped: a bare terminator carries
        no message.
        """
        while True:
            index = self.buffer.pending.find(self._terminator)
            if index < 0:
                # Only now, with no complete line left to rescue, is a large
                # buffer evidence of a lost terminator rather than of a burst
                # of good lines still waiting to be extracted.
                if len(self.buffer) > self._max_line_length:
                    logger.warning(
                        "PRT3: buffer overflow (%d bytes), discarding",
                        len(self.buffer),
                    )
                    self.buffer.clear()
                return None

            line = self.buffer.take(index + len(self._terminator))
            if line[: -len(self._terminator)].strip():
                return Frame(line)
