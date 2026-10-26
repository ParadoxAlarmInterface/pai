"""Serial connection protocol for the ``E0 FE`` wrapping.

The link starts plain: InitiateCommunication and its 37-byte ``72 FF``
identify reply are not wrapped. :meth:`E0FESerialConnectionProtocol.start_wrapping`
switches transmission over right before the identify echo, and from then on
every message is sent through :class:`~.e0fe.E0FECodec`.

Both directions share the codec's seq/seed state, so it cannot survive a lost
frame: once that happens the session is over and PAI has to reconnect with a
full handshake (see :meth:`E0FESerialConnectionProtocol.invalidate`). For the
same reason only one wrapped request may be outstanding at a time.
"""

import binascii
import logging
from typing import Any

from paradox.config import config
from paradox.connections.handler import ConnectionHandler
from paradox.connections.serial.e0fe import E0FECodec
from paradox.connections.serial.e0fe_framing import E0FESerialFramer
from paradox.connections.serial.protocol import SerialConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)

cfg: Any = config


def _is_live_event(message: bytes) -> bool:
    """Unsolicited ``Ex FF`` event: it is not the answer to any request."""
    return message[0] >> 4 == 0xE and message[1] == 0xFF


class E0FESerialConnectionProtocol(SerialConnectionProtocol):
    """``SerialConnectionProtocol`` for a link in ``E0 FE`` mode.

    Received ``72 FF`` identify frames are delivered as they are. ``E0 FE``
    frames are unwrapped, and the codec adopts their seq/seed before the
    message is handed on, events included. Wrapped frames that arrive before
    the handshake belong to no session of ours and are dropped, so the
    handshake always starts from seq/seed 0.

    Every protocol instance has its own codec. A reconnect builds a new
    instance, so it starts from a fresh state without any explicit reset.
    """

    def __init__(self, handler: ConnectionHandler) -> None:
        super().__init__(handler)  # type: ignore[no-untyped-call]
        self._framer = E0FESerialFramer()  # type: ignore[assignment]
        self._codec = E0FECodec()
        self._wrapping = False
        self._valid = True
        self._awaiting_reply = False
        self._last_request = b""

    def start_wrapping(self) -> None:
        """Wrap every message sent from now on, starting with the identify echo."""
        self._wrapping = True

    def awaiting_reply_to(self, message: bytes) -> bool:
        """True if ``message`` was the last wrapped request and is unanswered."""
        return (
            self._awaiting_reply and self._last_request == message and self.is_active()
        )

    def invalidate(self, reason: str) -> None:
        """End the session after a lost or undecodable frame.

        Nothing more is sent, received bytes are ignored, ``is_active()``
        turns false and the transport is closed. Idempotent.
        """
        if not self._valid:
            return
        self._valid = False
        logger.error("E0 FE: %s, closing the session", reason)
        self._framer.reset()
        if self.transport is not None:
            self.transport.close()

    def is_active(self) -> bool:
        return self._valid and super().is_active()

    def send_message(self, message: bytes) -> None:
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> SER %s", binascii.hexlify(message).decode())

        self.check_active()
        if not self._wrapping:
            frame = message
        elif self._awaiting_reply:
            raise ConnectionError("E0 FE: the previous request is still unanswered")
        else:
            # Wrapping advances the shared state, so nothing may run between
            # it and the write.
            frame = self._codec.wrap(message)
            self._awaiting_reply = True
            self._last_request = message
        assert self.transport is not None
        try:
            self.transport.write(frame)
        except Exception as e:
            self.invalidate("write failed")
            raise ConnectionError("E0 FE: write failed") from e

    def data_received(self, recv_data: bytes) -> None:
        if not self._valid:
            return

        for frame in self._framer.feed(recv_data):
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("SER -> PAI %s", binascii.hexlify(frame.data).decode())

            message = frame.data
            if frame.encrypted:
                if not self._wrapping:
                    logger.debug("E0 FE: dropping a wrapped frame before the handshake")
                    continue
                try:
                    message = self._codec.unwrap(frame.data)
                except ValueError as e:
                    self.invalidate(str(e))
                    return
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("SER UNWRAP: %s", binascii.hexlify(message).decode())
                if not _is_live_event(message):
                    self._awaiting_reply = False

            self.handler.on_message(message)
