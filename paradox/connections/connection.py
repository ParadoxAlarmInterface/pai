from abc import abstractmethod
import logging

from paradox.connections.handler import ConnectionHandler
from paradox.connections.protocol_base import ConnectionProtocol
from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger("PAI").getChild(__name__)


class Connection(AsyncMessageManager, ConnectionHandler):
    _protocol: ConnectionProtocol

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
        protocol = self._protocol
        try:
            if protocol is not None:
                await protocol.close()
        finally:
            # ConnectionProtocol.close() re-raises whatever killed the
            # transport -- the normal case when closing after a fault -- and
            # can also time out waiting for it to settle. Either way the
            # protocol is spent, so the reset has to happen regardless or the
            # next connect attempt inherits a dead one.
            self._protocol = None
            self.connected = False

    def variable_message_length(self, mode):
        if self._protocol is not None:
            self._protocol.variable_message_length(mode)
