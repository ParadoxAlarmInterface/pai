"""Framing for a serial link in ``E0 FE`` mode.

The framer handles both kinds of frame the panel sends on such a link:

* the plain 37-byte identify reply ``72 FF ...`` of the handshake, with an
  8-bit checksum;
* ``E0 FE`` frames carrying everything after it, with a little-endian 16-bit
  total length at bytes 2-3 and a little-endian 16-bit sum checksum at the end.

Pure byte handling: no asyncio, no transport, no decryption. ``E0 FE`` frames
are emitted with ``encrypted=True`` for :class:`~.e0fe.E0FECodec` to unwrap.
"""

import binascii
import logging
from typing import Optional

from paradox.connections.framing import Frame, Framer, checksum
from paradox.connections.serial.e0fe import (
    HEADER,
    MAX_FRAME_LENGTH,
    MIN_FRAME_LENGTH,
    is_frame,
)

logger = logging.getLogger("PAI").getChild(__name__)

IDENTIFY_HEADER = b"\x72\xff"
IDENTIFY_LENGTH = 37


class E0FESerialFramer(Framer):
    """Turns a wrapped serial byte stream into frames.

    Progress invariant (same contract as :class:`SerialFramer`): each
    :meth:`_next_frame` pass either emits a frame, consumes at least one byte
    to resynchronise, or returns ``None`` with fewer than
    :data:`~.e0fe.MAX_FRAME_LENGTH` bytes outstanding for the frame at the
    buffer head -- never waiting unbounded.
    """

    def _next_frame(self) -> Optional[Frame]:
        """Return the next :class:`Frame`, or ``None`` to wait for more data."""
        while True:
            head = self.buffer.peek(4)
            if not head:
                return None
            if head[0] not in (HEADER[0], IDENTIFY_HEADER[0]):
                self._discard("not a frame start")
                continue
            if len(head) < 2:
                return None

            if head[:2] == IDENTIFY_HEADER:
                length = IDENTIFY_LENGTH
                encrypted = False
            elif head[:2] == HEADER:
                if len(head) < 4:
                    return None
                length = int.from_bytes(head[2:4], "little")
                if not MIN_FRAME_LENGTH <= length <= MAX_FRAME_LENGTH:
                    self._discard("implausible length %d" % length)
                    continue
                encrypted = True
            else:
                self._discard("not a frame start")
                continue

            if len(self.buffer) < length:
                return None

            # Peek first: a checksum failure must cost exactly one byte, not a
            # whole speculative frame, or a single corrupt byte would swallow
            # real traffic behind it.
            candidate = self.buffer.peek(length)
            valid = is_frame(candidate) if encrypted else checksum(candidate)
            if not valid:
                self._discard("checksum mismatch")
                continue

            self.buffer.take(length)
            return Frame(candidate, encrypted=encrypted)

    def _discard(self, reason: str) -> None:
        dropped = self.buffer.discard()
        logger.debug(
            "E0 FE: discarding byte %s (%s)", binascii.hexlify(dropped).decode(), reason
        )
