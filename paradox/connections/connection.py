import asyncio
import logging

logger = logging.getLogger('PAI').getChild(__name__)

class ConnectionProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.read_queue = asyncio.Queue()

    def connection_made(self, transport):
        self.transport = transport

    def close(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def connection_lost(self, exc):
        self.read_queue = asyncio.Queue()

class Connection:
    def __init__(self, timeout=5.0):
        self.connected = False
        self.connection = None
        self.default_timeout = timeout

    async def connect(self):
        raise NotImplementedError("Implement in subclass")

    def write(self, data):
        if self.connected:
            self.connection.send_message(data)
        else:
            raise ConnectionError("Failed to write data to connection")

    async def read(self, timeout=None):
        """Read data from the IP Port, if available, until the timeout is exceeded"""

        if not timeout:
            timeout = self.default_timeout

        if self.connected:
            result = await self.connection.read_message(timeout=timeout)
        else:
            raise ConnectionError("Unable to read data. Not connected")

        return result

    def timeout(self, timeout=5.0):
        self.default_timeout = timeout

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
        self.connected = False
