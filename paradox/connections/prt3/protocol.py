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
from paradox.connections.protocols import ConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)


class PRT3Protocol(ConnectionProtocol):
    """
    Framing protocol for the PRT3 ASCII serial interface.

    Buffers incoming bytes and emits complete \\r-terminated lines as
    ``bytes`` objects to the connection handler.  The \\r byte is included
    in the emitted bytes so the handler can verify framing; PRT3Panel's
    parse_message() strips it before calling parse_line().
    """

    def variable_message_length(self, *args, **kwargs):
        # PRT3 lines are delimiter-framed, not length-prefixed.
        # This is a deliberate no-op so the Panel base class can call it
        # without error; actual line assembly happens in data_received().
        pass

    def data_received(self, data: bytes):
        """
        Buffer incoming bytes and emit each complete \\r-terminated line.

        Lines that contain no printable content after stripping whitespace
        are silently discarded (e.g. a bare \\r with no preceding payload).
        """
        self.buffer += data

        if len(self.buffer) > 512:  # PRT3 max line is ~21 bytes; 512 is generous
            logger.warning(
                "PRT3: buffer overflow (%d bytes), discarding", len(self.buffer)
            )
            self.buffer = b""
            return

        while b"\r" in self.buffer:
            line, self.buffer = self.buffer.split(b"\r", 1)
            line_with_cr = line + b"\r"

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PRT3 <- %s", binascii.hexlify(line_with_cr))

            if line.strip():   # skip empty / whitespace-only lines
                self.handler.on_message(line_with_cr)

    def send_message(self, message: bytes):
        """
        Write raw ASCII bytes directly to the transport.

        PRT3 commands are already \\r-terminated by encoder.py; no additional
        framing is added here.
        """
        self.check_active()

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PRT3 -> %s", binascii.hexlify(message))

        self.transport.write(message)
