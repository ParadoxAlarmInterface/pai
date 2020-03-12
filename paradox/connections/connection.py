import asyncio
import logging
import typing

from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger("PAI").getChild(__name__)


class Connection(AsyncMessageManager):
    def __init__(self, on_message: typing.Callable[[bytes], None]):
        super().__init__()
        self.connected = False
        self._protocol = None  # type: ConnectionProtocol
        self.on_message = on_message

    async def connect(self):
        raise NotImplementedError("Implement in subclass")

    def write(self, data: bytes):
        if self.connected:
            self._protocol.send_message(data)
        else:
            raise ConnectionError("Failed to write data to connection")

    async def close(self):
        if self._protocol:
            await self._protocol.close()
            self._protocol = None
        self.connected = False

    def variable_message_length(self, mode):
        if self._protocol is not None:
            self._protocol.variable_message_length(mode)
