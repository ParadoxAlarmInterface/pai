"""Framing for the Paradox serial / Combus wire protocol.

Pure byte handling: no asyncio, no transport, no decryption. The protocol class
adds those. Keeping derivation separate is what lets every rule below be tested
against real captures with plain ``bytes``.
"""

import binascii
import logging
from typing import Iterator

from paradox.config import config as cfg
from paradox.connections.framing import (
    NEED_MORE,
    RESYNC,
    Derivation,
    Frame,
    FrameBuffer,
    FrameLength,
    checksum,
)

logger = logging.getLogger("PAI").getChild(__name__)

#: Shortest and longest plausible unencrypted serial frame. A length derived
#: outside this range means the buffer head is misaligned (e.g. after a lost
#: serial byte), not that a real frame is on its way.
MIN_MESSAGE_LENGTH = 4
MAX_MESSAGE_LENGTH = 71

#: Frames with no length field: fixed-size legacy messages.
FIXED_MESSAGE_LENGTH = 37

#: Nibbles whose byte 1 carries a length, but only within the plausible range;
#: anything else means the byte is payload and the frame is fixed length.
#: Note 0x2 is deliberately absent, matching long-standing behaviour.
BOUNDED_LENGTH_NIBBLES = frozenset([1, 3, 4, 5, 6, 7, 8, 9])

#: Nibbles whose byte 1 is unconditionally the length.
DIRECT_LENGTH_NIBBLES = frozenset([0xA, 0xB, 0xD])

#: An EVO payload maxes out at 71 bytes, which is 5 AES blocks. 7 is headroom.
#: The bound matters: it caps how far the framer will scan before giving up and
#: resynchronising, which is what keeps a corrupt stream from stalling the link.
MAX_AES_BLOCKS = 7

#: Largest buffer the AES scan will ever examine for one frame.
MAX_AES_FRAME_LENGTH = 2 + MAX_AES_BLOCKS * 16 + 1


class SerialFramer:
    """Turns a serial byte stream into frames.

    Progress invariant: every pass of :meth:`feed` either emits a frame,
    consumes at least one byte, or returns with a bounded buffer. Violating it
    is what caused every stall defect this class replaces.
    """

    def __init__(self, use_variable_message_length: bool = True) -> None:
        self.buffer = FrameBuffer()
        self.use_variable_message_length = use_variable_message_length
        # Read once here rather than per byte; the connection is rebuilt when
        # configuration changes.
        self._encrypted_link = bool(cfg.SERIAL_ENCRYPTED)

    def reset(self) -> None:
        self.buffer.clear()

    def feed(self, data: bytes) -> Iterator[Frame]:
        """Append ``data`` and yield every complete frame it completes.

        A generator rather than a list: if the consumer raises while handling
        frame *n*, frames *n+1..* remain buffered and are re-parsed on the next
        feed instead of being silently dropped.
        """
        self.buffer.append(data)
        try:
            while True:
                frame = self._next_frame()
                if frame is None:
                    return
                yield frame
        finally:
            self.buffer.compact()

    def _next_frame(self):
        """Return the next :class:`Frame`, or ``None`` to wait for more data."""
        while True:
            if not self.use_variable_message_length:
                if len(self.buffer) < FIXED_MESSAGE_LENGTH:
                    return None
                frame = self._take_checked(FrameLength(FIXED_MESSAGE_LENGTH))
                if frame is not None:
                    return frame
                # Checksum failed and one byte was consumed; realign and retry.
                continue

            if len(self.buffer) < MIN_MESSAGE_LENGTH:
                return None

            result = self.derive_length(self.buffer[: min(len(self.buffer), 3)])

            if result is NEED_MORE:
                return None
            if result is RESYNC:
                self._discard("implausible header")
                continue

            if len(self.buffer) < result.length:
                return None

            frame = self._take_checked(result)
            if frame is not None:
                return frame
            # Checksum failed: one byte was consumed, so try again from the
            # next possible frame start.

    def _take_checked(self, result: FrameLength):
        """Consume ``result.length`` bytes if they form a valid frame.

        Peeks first: a checksum failure must cost exactly one byte, not a whole
        speculative frame, or a single corrupt byte would swallow real traffic
        behind it.
        """
        candidate = self.buffer.peek(result.length)

        # Encrypted frames were already validated by the checksum scan, or (for
        # BabyWare compact frames) carry no checksum at all.
        if not result.encrypted and not checksum(candidate):
            self._discard("checksum mismatch")
            return None

        self.buffer.take(result.length)
        return Frame(candidate, encrypted=result.encrypted)

    def _discard(self, reason: str) -> None:
        dropped = self.buffer.discard()
        if dropped:
            logger.debug(
                "SER: discarding byte %s (%s)",
                binascii.hexlify(dropped).decode(),
                reason,
            )

    def derive_length(self, head: bytes) -> Derivation:
        """Derive the frame length from up to the first three bytes.

        Returns a :class:`FrameLength`, ``NEED_MORE`` when more header bytes are
        required, or ``RESYNC`` when the head cannot begin a frame.
        """
        nibble = head[0] >> 4

        if nibble == 0xE and len(head) >= 2 and head[1] == 0xFE:
            return self._derive_e0fe(head)

        if nibble == 0:
            length = FIXED_MESSAGE_LENGTH
        elif nibble in BOUNDED_LENGTH_NIBBLES:
            length = (
                head[1] if 0 < head[1] <= MAX_MESSAGE_LENGTH else FIXED_MESSAGE_LENGTH
            )
        elif nibble in DIRECT_LENGTH_NIBBLES:
            length = head[1]
        elif nibble == 0xC:
            if len(head) < 3:
                return NEED_MORE
            length = head[1] * 256 + head[2]
        elif nibble == 0xE:
            # MG/SP in the 21st century and EVO live events. Probable values
            # for byte 1 are 0x13, 0x00 and 0xFF, which are payload, not length.
            if head[1] < FIXED_MESSAGE_LENGTH or head[1] == 0xFF:
                length = FIXED_MESSAGE_LENGTH
            else:
                length = head[1]
        else:
            length = FIXED_MESSAGE_LENGTH

        if not MIN_MESSAGE_LENGTH <= length <= MAX_MESSAGE_LENGTH:
            # Length synthesised from a misaligned payload byte, e.g. a battery
            # voltage byte 0xC0-0xCF at the head reads as ~39000 bytes. Waiting
            # for it would block the framer for minutes without consuming a
            # byte, so resynchronise instead.
            logger.warning(
                "SER: implausible message length %d derived from %s, resyncing",
                length,
                binascii.hexlify(head).decode(),
            )
            return RESYNC

        return FrameLength(length)

    def _derive_e0fe(self, head: bytes) -> Derivation:
        if self._encrypted_link:
            return self._scan_aes_blocks()

        # BabyWare compact E0 FE: the length is byte 2 and the frame carries no
        # checksum, so it is exempt from the plausible-length range.
        if len(head) < 3:
            return NEED_MORE
        length = head[2]
        if length < MIN_MESSAGE_LENGTH:
            # Framing a zero-length frame would consume nothing and spin.
            logger.warning("SER: implausible E0FE length %d, resyncing", length)
            return RESYNC
        return FrameLength(length, encrypted=True)

    def _scan_aes_blocks(self) -> Derivation:
        """Find a full-AES ``E0 FE`` frame boundary by checksum.

        The frame is ``[E0|x][FE][n*16 AES bytes][checksum]`` with no length
        field, so the only way to find its end is to test each block boundary.
        """
        available = len(self.buffer)
        for n_blocks in range(1, MAX_AES_BLOCKS + 1):
            frame_len = 2 + n_blocks * 16 + 1
            if available < frame_len:
                # Not enough data to test this boundary yet, and every later
                # boundary is longer still.
                return NEED_MORE
            if checksum(self.buffer.peek(frame_len)):
                return FrameLength(frame_len, encrypted=True)

        # Every boundary tested and none checksummed. This is not a frame.
        # Returning NEED_MORE here is what used to wedge the link: the buffer
        # grew without bound and the handler was never called again.
        logger.warning(
            "SER: no valid AES frame within %d bytes of %s, resyncing",
            MAX_AES_FRAME_LENGTH,
            binascii.hexlify(self.buffer.peek(3)).decode(),
        )
        return RESYNC
