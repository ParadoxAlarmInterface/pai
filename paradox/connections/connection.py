import asyncio
import logging
import typing

from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger('PAI').getChild(__name__)


class ConnectionProtocol(asyncio.Protocol):
    def __init__(self, on_message: typing.Callable[[bytes], None], on_con_lost):
        self.transport = None
        self.use_variable_message_length = True
        self.on_message = on_message
        self.on_con_lost = on_con_lost

    def connection_made(self, transport):
        self.transport = transport

    def close(self):
        if self.transport:
            try:
                self.transport.close()
            except Exception:
                logger.exception("Connection transport close raised Exception")
            self.transport = None

    def send_message(self, message):
        raise NotImplementedError('This function needs to be overridden in a subclass')

    def connection_lost(self, exc):
        self.close()
        self.on_con_lost()

    def variable_message_length(self, mode):
        self.use_variable_message_length = mode


class Connection(AsyncMessageManager):
    def __init__(self, on_message: typing.Callable[[bytes], None]):
        super().__init__()
        self.connected = False
        self.connection = None  # type: ConnectionProtocol
        self.on_message = on_message

    async def connect(self):
        raise NotImplementedError("Implement in subclass")

    def write(self, data: bytes):
        if self.connected:
            self.connection.send_message(data)
        else:
            raise ConnectionError("Failed to write data to connection")

    def close(self):
        logger.info('Closing connection')

        if self.connection:
            self.connection.close()
            self.connection = None
        self.connected = False

    def variable_message_length(self, mode):
        if self.connection is not None:
            self.connection.variable_message_length(mode)
