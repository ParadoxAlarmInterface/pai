"""
PRT3Protocol — asyncio.Protocol for the Paradox PRT3 Printer Module.

The PRT3 module speaks a plain ASCII protocol over serial:
  - Every message from the panel is terminated with \\r (0x0D).
  - Commands sent to the panel are raw ASCII bytes, also \\r-terminated.
  - There is no binary framing, no checksum byte, and no variable-length
    nibble-pattern header — none of SerialConnectionProtocol applies here.

This class buffers incoming bytes and emits complete \\r-delimited lines
to the owning connection handler via on_message().
"""

import binascii
import logging

from paradox.config import config as cfg
from paradox.connections.framing import LineFramer
from paradox.connections.protocol_base import ConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)

#: PRT3 lines are ~21 bytes; anything much larger means the delimiter was lost.
MAX_LINE_LENGTH = 512


class PRT3Protocol(ConnectionProtocol):
    """
    Framing protocol for the PRT3 ASCII serial interface.

    Buffers incoming bytes and emits complete \\r-terminated lines as
    ``bytes`` objects to the connection handler.  The \\r byte is included
    in the emitted bytes so the handler can verify framing; PRT3Panel's
    parse_message() strips it before calling parse_line().
    """

    def __init__(self, handler):
        super().__init__(handler)
        self._framer = LineFramer(
            terminator=b"\r",
            max_line_length=MAX_LINE_LENGTH,
            drop_blank_lines=True,
        )

    def variable_message_length(self, *args, **kwargs):
        # PRT3 lines are delimiter-framed, not length-prefixed.
        # This is a deliberate no-op so the Panel base class can call it
        # without error; actual line assembly happens in the framer.
        pass

    def data_received(self, data: bytes):
        """Emit each complete \\r-terminated line to the handler."""
        for frame in self._framer.feed(data):
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PRT3 <- %s", binascii.hexlify(frame.data))
            self.handler.on_message(frame.data)

    def reset_framing(self) -> None:
        self._framer.reset()

    @property
    def buffer(self) -> bytes:
        """Unconsumed bytes. Retained for tests and diagnostics."""
        return self._framer.buffer.pending

    def send_message(self, message: bytes):
        """
        Write raw ASCII bytes directly to the transport.

        PRT3 commands are already \\r-terminated by encoder.py; no additional
        framing is added here.
        """
        self.check_active()

        if cfg.LOGGING_DUMP_PACKETS:
            # AA (arm with code) and AD (disarm) embed the user code in the
            # payload; show only the command prefix to keep it out of logs.
            if message[:2] in (b"AA", b"AD"):
                logger.debug("PRT3 -> %s<redacted>", binascii.hexlify(message[:5]))
            else:
                logger.debug("PRT3 -> %s", binascii.hexlify(message))

        self.transport.write(message)
