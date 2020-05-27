import logging
import typing

from paradox.connections.protocols import ConnectionProtocol
from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger("PAI").getChild(__name__)


class Connection(AsyncMessageManager):
    def __init__(self, on_message: typing.Callable[[bytes], None]):
        super().__init__()
        self._connected = False
        self._protocol = None  # type: ConnectionProtocol
        self._on_message = on_message

    def on_message(self, raw: bytes):
        self._on_message(raw)

    @property
    def connected(self) -> bool:
        return self._connected and self._protocol and self._protocol.is_active()

    @connected.setter
    def connected(self, value: bool):
        self._connected = value

    async def connect(self) -> bool:
        raise NotImplementedError("Implement in subclass")

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

    def variable_message_length(self, mode):
        if self._protocol is not None:
            self._protocol.variable_message_length(mode)
