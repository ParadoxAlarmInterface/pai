"""Framing for the IP150 / IP100 module wire protocol."""

import binascii
import logging
from typing import Iterator

from paradox.connections.framing import (
    NEED_MORE,
    RESYNC,
    Derivation,
    Frame,
    FrameBuffer,
    FrameLength,
)

logger = logging.getLogger("PAI").getChild(__name__)

#: Start of frame marker.
SOF = 0xAA

#: The header is a fixed 16 byte aligned block.
IP_HEADER_LENGTH = 16

#: Offsets within the header.
_LENGTH_OFFSET = 1
_FLAGS_OFFSET = 4

#: Bit 0 of the flags byte marks an encrypted, and therefore 16 byte aligned,
#: payload. An unencrypted payload is exactly ``length`` bytes.
_ENCRYPT_FLAG = 0x01

#: Any declared payload beyond this is a desynchronised stream, not a message.
#: Observed payloads are well under 100 bytes; upload/download leaves headroom.
MAX_IP_PAYLOAD = 2048


class IPFramer:
    """Turns an IP150 byte stream into framed messages.

    Unlike the serial framer this does not slide byte by byte on desync. The
    transport is TCP, so a stream that does not begin with a valid header is
    corrupt rather than merely offset; sliding through it would only
    manufacture plausible-looking garbage.
    """

    def __init__(self) -> None:
        self.buffer = FrameBuffer()

    def reset(self) -> None:
        self.buffer.clear()

    def feed(self, data: bytes) -> Iterator[Frame]:
        """Append ``data`` and yield every complete message it completes."""
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
        if len(self.buffer) < IP_HEADER_LENGTH:
            return None

        result = self.derive_length(self.buffer.peek(IP_HEADER_LENGTH))

        if result is NEED_MORE:
            return None
        if result is RESYNC:
            self._drop_buffer()
            return None

        if len(self.buffer) < result.length:
            return None

        return Frame(self.buffer.take(result.length), encrypted=result.encrypted)

    def _drop_buffer(self) -> None:
        logger.warning(
            "Dangling data in the receive buffer: %s",
            binascii.hexlify(self.buffer.peek(64)).decode(),
        )
        self.buffer.clear()

    def derive_length(self, head: bytes) -> Derivation:
        """Derive the total message length from the 16 byte header."""
        if len(head) < IP_HEADER_LENGTH:
            return NEED_MORE

        if head[0] != SOF:
            return RESYNC

        payload_length = head[_LENGTH_OFFSET] | (head[_LENGTH_OFFSET + 1] << 8)
        if payload_length > MAX_IP_PAYLOAD:
            logger.warning(
                "IP: implausible payload length %d, dropping buffer", payload_length
            )
            return RESYNC

        encrypted = bool(head[_FLAGS_OFFSET] & _ENCRYPT_FLAG)
        if encrypted:
            # Only an encrypted payload is padded up to a 16 byte boundary.
            payload_length += (-payload_length) % 16

        return FrameLength(IP_HEADER_LENGTH + payload_length, encrypted=encrypted)
