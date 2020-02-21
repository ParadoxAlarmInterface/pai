import asyncio
import logging
import typing

from paradox.lib.async_message_manager import AsyncMessageManager

logger = logging.getLogger('PAI').getChild(__name__)


class ConnectionProtocol(asyncio.Protocol):
    def __init__(self, on_message: typing.Callable[[bytes], None], on_con_lost):
        self.transport = None
        self.use_variable_message_length = True
        self.buffer = b''

        self.on_message = on_message
        self.on_con_lost = on_con_lost

        self._closed = asyncio.get_event_loop().create_future()
        self.buffer = b''

    def connection_made(self, transport):
        logger.info("Connection made")
        self.transport = transport

    def is_closing(self):
        return self.transport.is_closing()

    async def close(self):
        if self.transport:
            logger.info('Closing transport')
            try:
                self.transport.close()
            except Exception:
                logger.exception("Connection transport close raised Exception")
            self.transport = None

        await asyncio.wait_for(self._closed, timeout=1)

    def send_message(self, message):
        raise NotImplementedError('This function needs to be overridden in a subclass')

    def connection_lost(self, exc):
        logger.error(f'Connection was closed: {exc}')
        self.buffer = b''

        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)

        super().connection_lost(exc)

        asyncio.get_event_loop().call_soon(self.on_con_lost)

        self.on_message = None
        self.on_con_lost = None

    def variable_message_length(self, mode):
        self.use_variable_message_length = mode

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed.done() and not closed.cancelled():
            closed.exception()


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
        logger.info('Closing connection')

        if self._protocol:
            await self._protocol.close()
            self._protocol = None
        self.connected = False

    def variable_message_length(self, mode):
        if self._protocol is not None:
            self._protocol.variable_message_length(mode)
