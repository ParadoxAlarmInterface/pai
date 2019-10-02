import asyncio
import logging

logger = logging.getLogger('PAI').getChild(__name__)

class ConnectionProtocol(asyncio.Protocol):
    def __init__(self, on_con_lost):
        self.transport = None
        self.read_queue = asyncio.Queue()
        self.use_variable_message_length = True
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

    async def read_message(self, timeout=5):
        raise NotImplementedError('This function needs to be overridden in a subclass')

    def connection_lost(self, exc):
        self.read_queue = asyncio.Queue()
        self.close()
        self.on_con_lost()

    def variable_message_length(self, mode):
        self.use_variable_message_length = mode

class Connection:
    def __init__(self, timeout=5.0):
        self.connected = False
        self.connection = None  # type: ConnectionProtocol
        self.default_timeout = timeout

    async def connect(self):
        raise NotImplementedError("Implement in subclass")

    def write(self, data: bytes):
        if self.connected:
            self.connection.send_message(data)
        else:
            raise ConnectionError("Failed to write data to connection")

    async def read(self, timeout=None):
        """Read data from the IP Port, if available, until the timeout is exceeded"""

        if not self.connection or not self.connection.transport:
            raise ConnectionError("Unable to read data. Connection transport not connected")

        if not timeout:
            timeout = self.default_timeout

        return await self.connection.read_message(timeout=timeout)

    def timeout(self, timeout=5.0):
        self.default_timeout = timeout

    def close(self):
        logger.info('Closing connection')

        if self.connection:
            self.connection.close()
            self.connection = None
        self.connected = False

    def variable_message_length(self, mode):
        if self.connection is not None:
            self.connection.variable_message_length(mode)
