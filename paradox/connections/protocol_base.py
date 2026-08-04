"""Shared asyncio glue for all PAI connection protocols.

Framing lives in the ``framing`` modules; this class owns only transport
lifecycle. The split keeps each concern testable on its own.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

from paradox.config import config as cfg
from paradox.connections.handler import ConnectionHandler

logger = logging.getLogger("PAI").getChild(__name__)


class ConnectionProtocol(asyncio.Protocol, ABC):
    """Base for connection protocols.

    ``ABC`` is mixed in deliberately: ``asyncio.Protocol`` uses the plain
    ``type`` metaclass, so ``@abstractmethod`` alone is inert and an incomplete
    subclass would instantiate happily and fail only when called.
    """

    def __init__(self, handler: ConnectionHandler):
        self.transport = None
        self.handler = handler
        self._closed: Optional[asyncio.Future] = None

    def connection_made(self, transport):
        self._closed = asyncio.get_running_loop().create_future()
        self.transport = transport
        self.handler.on_connection()

    def is_active(self) -> bool:
        return (
            bool(self.transport)
            and self._closed is not None
            and not self._closed.done()
        )

    def check_active(self) -> None:
        if not self.is_active():
            raise ConnectionError("Transport does not exist or is already closed")

    async def close(self):
        if self.transport:
            try:
                self.transport.close()
            except Exception:
                logger.exception("Connection transport close raised Exception")
            self.transport = None

        if self._closed is not None:
            await asyncio.wait_for(self._closed, timeout=cfg.IO_TIMEOUT)

    @abstractmethod
    def send_message(self, message):
        raise NotImplementedError("This function needs to be overridden in a subclass")

    def reset_framing(self) -> None:
        """Drop any partially received frame. Overridden where framing exists."""

    def variable_message_length(self, mode: bool) -> None:
        """Toggle variable-length framing. Overridden where framing exists."""

    @property
    def use_variable_message_length(self) -> bool:
        return True

    def connection_lost(self, exc):
        if exc is None:
            logger.info("Connection was closed")
        else:
            logger.error("Connection was closed: %s", exc)

        self.reset_framing()
        self.transport = None

        if self._closed is not None and not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)

        super().connection_lost(exc)

        self.handler.on_connection_loss()
        self.handler = None

    def __del__(self):
        # Retrieve the exception so asyncio does not report it as unhandled.
        closed = self._closed
        if closed is not None and closed.done() and not closed.cancelled():
            closed.exception()
