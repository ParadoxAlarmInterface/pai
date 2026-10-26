from abc import abstractmethod
import logging
from typing import Awaitable, Callable, Optional

from construct import Container

from paradox.connections.handler import ConnectionHandler
from paradox.connections.protocol_base import ConnectionProtocol
from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger("PAI").getChild(__name__)

Exchange = Callable[
    [bytes, Callable[[Container], bool]], Awaitable[Optional[Container]]
]
"""Send a raw message and await the first parsed reply accepted by the check."""


class Connection(AsyncMessageManager, ConnectionHandler):
    """Base for all panel links.

    Besides the transport, a connection may take part in the session the
    panel sees. ``Paradox`` calls the hooks below at fixed points; the
    defaults keep the plain behaviour every existing connection relies on.
    """

    _protocol: ConnectionProtocol

    #: ``source_id`` sent in StartCommunication.
    start_communication_source_id: int = 0x2

    #: Whether ``Paradox.send_wait()`` may resend a request after a timeout.
    #: Disable it for links where a lost reply leaves the session state
    #: unknown, so a timeout propagates after the first attempt.
    retransmit_requests: bool = True

    def __init__(self):
        super().__init__()
        self.connected = False
        self._protocol: ConnectionProtocol = None

    def on_message(self, raw: bytes):
        self.schedule_raw_message_handling(raw)

    def on_connection(self):
        logger.info("Connection established")

    def on_connection_loss(self):
        logger.error("Connection was lost")
        self.connected = False

    @property
    def connected(self) -> bool:
        return (
            self._connected
            and self._protocol is not None
            and self._protocol.is_active()
        )

    @connected.setter
    def connected(self, value: bool):
        self._connected = value

    @abstractmethod
    async def connect(self) -> bool:
        raise NotImplementedError("Implement in a subclass")

    def write(self, data: bytes):
        if self.connected:
            self._protocol.send_message(data)  # throws ConnectionError
        else:
            raise ConnectionError("Not connected")

    async def close(self):
        if self._protocol:
            await self._protocol.close()
            self._protocol = None
        self.connected = False

    async def on_initiate_communication(
        self, reply: Container, exchange: Exchange
    ) -> None:
        """Called once the panel answered InitiateCommunication.

        Runs before StartCommunication (or, for panels that skip it, before
        the panel object is recreated). ``exchange`` sends through
        ``Paradox.send_wait()``, so it holds the request lock and honours
        ``retransmit_requests``. Raise ``ConnectionError`` to abort the
        connect.
        """

    async def end_session(self) -> None:
        """Called on disconnect while connected, after CloseConnection was sent.

        The transport is closed right after this returns, raises or is
        cancelled. Implementations bound their own waiting and do not wait on
        ``Paradox.request_lock``: disconnect may run while a request holds it.
        """

    def variable_message_length(self, mode):
        if self._protocol is not None:
            self._protocol.variable_message_length(mode)

    def set_framer(self, framer):
        """Swap the protocol's framer at runtime (after panel detection)."""
        if self._protocol is not None:
            self._protocol.set_framer(framer)
