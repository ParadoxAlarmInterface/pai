"""Framing for the Paradox MG6250 WinLoad/PID0004 serial protocol.

    DE | cmd (LE16) | LEN (LE16) | lenA | lenB | A | B | body... | CRC16-MODBUS (LE)

``LEN`` (bytes 3-4) is the whole frame length including the 2 CRC bytes, and
the last two bytes are a CRC-16/MODBUS over everything before them,
little-endian. ``A``/``B`` are optional fields whose lengths are bytes 5 and 6

Pure byte handling: no asyncio, no transport, no decryption. The 0x24 payloads
are AES-encrypted *inside* the frame (handled by the panel layer, not here), so
every frame this framer emits is marked ``encrypted=False`` at the link level.
"""

import logging
from typing import Optional

from paradox.connections.framing import Frame, Framer

logger = logging.getLogger("PAI").getChild(__name__)

SOF = 0xDE
HEADER_LEN = 7  # DE, cmd (LE16), LEN (LE16), lenA, lenB
CHECKSUM_LEN = 2  # CRC16-MODBUS
OVERHEAD = HEADER_LEN + CHECKSUM_LEN  # 9
LENGTH_OFFSET = 3  # LEN is bytes 3-4, little-endian
MIN_MESSAGE_LENGTH = OVERHEAD
# LEN is 16-bit, but the longest frame seen is 253 bytes; a tighter bound keeps
# the wait on a false 0xDE short.
MAX_MESSAGE_LENGTH = 4096


def crc16_modbus(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")


class MG6250SerialFramer(Framer):
    """Turns the MG6250 serial byte stream into whole, CRC-checked frames.

    Progress invariant (same contract as :class:`SerialFramer`): each
    :meth:`_next_frame` pass either emits a frame, consumes at least one byte
    to resynchronise, or returns ``None`` needing at most ``MAX_MESSAGE_LENGTH``
    further bytes -- never waiting unbounded.
    """

    def _next_frame(self) -> Optional[Frame]:
        while True:
            # 1. find the start-of-frame marker, dropping junk before it
            start = self.buffer.find(bytes([SOF]))
            if start < 0:
                # No SOF in the buffer: drop everything so it cannot grow
                # unbounded.
                if len(self.buffer):
                    self.buffer.take(len(self.buffer))
                return None
            if start > 0:
                self.buffer.discard(start)  # realign to the SOF

            # 2. need the length field
            if len(self.buffer) < LENGTH_OFFSET + 2:
                return None
            length = int.from_bytes(
                self.buffer.peek(LENGTH_OFFSET + 2)[LENGTH_OFFSET:], "little"
            )

            # 3. implausible length -> this 0xDE is not a real header; resync
            if not (MIN_MESSAGE_LENGTH <= length <= MAX_MESSAGE_LENGTH):
                self.buffer.discard(1)
                continue

            # 4. wait for the whole frame
            if len(self.buffer) < length:
                return None

            candidate = self.buffer.peek(length)

            # 5. validate CRC16 over everything but the last 2 bytes
            if crc16_modbus(candidate[:-CHECKSUM_LEN]) != candidate[-CHECKSUM_LEN:]:
                logger.debug("MG6250: CRC mismatch, resyncing past 0xDE")
                self.buffer.discard(1)  # cost one byte, not the whole candidate
                continue

            self.buffer.take(length)
            return Frame(candidate, encrypted=False)
