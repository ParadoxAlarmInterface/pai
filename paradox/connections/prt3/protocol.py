"""
PRT3Protocol — asyncio.Protocol for the Paradox PRT3 Printer Module.

The PRT3 module speaks a plain ASCII protocol over serial:
  - Every message from the panel is terminated with \\r (0x0D).
  - Commands sent to the panel are raw ASCII bytes, also \\r-terminated.
  - There is no binary framing, no checksum byte, and no variable-length
    nibble-pattern header — none of SerialConnectionProtocol applies here.

This class buffers incoming bytes and emits complete \\r-delimited lines
to the owning connection handler via on_message().

TODO (Phase 2): Implement data_received() line framer.
TODO (Phase 2): Implement send_message() raw write.
"""

import logging

from paradox.connections.protocols import ConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)


class PRT3Protocol(ConnectionProtocol):
    """
    Framing protocol for the PRT3 ASCII serial interface.

    Buffers incoming bytes and emits complete ASCII lines (\\r-terminated)
    as ``bytes`` objects to the connection handler.
    """

    def variable_message_length(self, *args, **kwargs):
        # PRT3 lines have no fixed length — framing is delimiter-based.
        # This method is a deliberate no-op so the Panel base class can call
        # it without error; actual line assembly happens in data_received().
        pass

    def data_received(self, data: bytes):
        # TODO (Phase 2): Buffer incoming bytes; emit complete \r-delimited
        # lines via self.handler.on_message(line).
        raise NotImplementedError(
            "PRT3Protocol.data_received() not yet implemented — see Phase 2"
        )

    def send_message(self, message: bytes):
        # TODO (Phase 2): Write raw bytes directly to self.transport.
        # PRT3 commands are plain ASCII, already \\r-terminated by encoder.py.
        raise NotImplementedError(
            "PRT3Protocol.send_message() not yet implemented — see Phase 2"
        )
