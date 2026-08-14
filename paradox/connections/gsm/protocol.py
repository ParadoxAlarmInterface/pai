"""Framing and echo suppression for an AT-command GSM modem.

Pure asyncio glue over :class:`~paradox.connections.framing.LineFramer`: no
AT-command knowledge lives here beyond the echo of the last write.
"""

import logging

from paradox.connections.framing import LineFramer
from paradox.connections.handler import ConnectionHandler
from paradox.connections.protocol_base import ConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)

#: AT responses are short, but a text-mode ``+CMT`` line carries a whole SMS:
#: 140 octets of UCS2 hex-encoded payload plus the header. 1 KiB leaves room
#: for that and for verbose ``AT+CMEE=2`` error strings.
MAX_LINE_LENGTH = 1024

TERMINATOR = b"\r\n"


class GsmSerialProtocol(ConnectionProtocol):
    """CRLF line framing and modem echo suppression for an AT-command modem.

    Named apart from
    :class:`paradox.connections.serial.protocol.SerialConnectionProtocol`
    because the two are not substitutable: that one's ``send_message`` is
    synchronous, this one's is a coroutine.
    """

    def __init__(self, handler: ConnectionHandler):
        super().__init__(handler)
        self.last_message = b""
        self._framer = LineFramer(
            terminator=TERMINATOR,
            max_line_length=MAX_LINE_LENGTH,
            strip_terminator=True,
        )

    async def send_message(self, message):
        self.last_message = message
        self.transport.write(message + TERMINATOR)

    def data_received(self, recv_data):
        for frame in self._framer.feed(recv_data):
            message = frame.data
            logger.debug("M->P: %s", message)

            if self._is_echo(message):
                continue

            try:
                self.handler.on_message(message)
            except Exception:
                # A single unparseable line must not strand the frames behind
                # it: they would sit in the buffer until the next byte arrives.
                logger.exception("Error handling modem message")

    def _is_echo(self, message: bytes) -> bool:
        """True when ``message`` is the modem echoing back the last command.

        Echo suppression is scoped to the first line after a write. Echo is
        normally off (``connect()`` issues ``ATE0``), so an expectation that
        outlived its response would eventually swallow an unrelated line that
        happened to match the last command.

        The comparison tolerates a trailing ``\\r`` because many V.25ter modems
        echo the command terminated by a bare ``<CR>`` and only then send
        ``<CR><LF>OK<CR><LF>``.
        """
        expected, self.last_message = self.last_message, b""
        return bool(expected) and message.rstrip(b"\r") == expected.rstrip(b"\r")

    def reset_framing(self) -> None:
        self._framer.reset()
        self.last_message = b""

    @property
    def buffer(self) -> bytes:
        """Unconsumed bytes. Retained for tests and diagnostics."""
        return self._framer.buffer.pending

    def connection_lost(self, exc):
        logger.error("The serial port was closed")
        self.last_message = b""
        super().connection_lost(exc)
