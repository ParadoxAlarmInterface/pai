# -*- coding: utf-8 -*-

import binascii
import logging
import time

import asyncio
import serial_asyncio

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

last = 0
def checksum(data):
    """Calculates the 8bit checksum of Paradox messages"""
    c = 0

    if data is None or len(data) < 37:
        return False

    for i in data[:36]:
        c += i

    r = (c % 256) == data[36]
    return r

class SerialConnectionProtocol(asyncio.Protocol):
    def __init__(self, on_port_open, on_port_closed):
        self.buffer = b''
        self.transport = None
        self.read_queue = asyncio.Queue()
        self.on_port_open = on_port_open
        self.on_port_closed = on_port_closed
        self.last_sent_message_time = 0
        self.loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        logger.info("Serial port Open")
        self.transport = transport
        self.on_port_open()
 
    async def _send_message(self, message):
        await self.transport.write(message)
        self.last_sent_message_time = time.time()

    def send_message(self, message):
        
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PC -> Serial {}".format(binascii.hexlify(message)))
        
        # Panels seem to throttle messages
        # Impose 100ms between commands. 
        # Value needs to be tweaked, or removed
        # TODO: Investigate this
        now = time.time()
        elapsed = now - self.last_sent_message_time
        throttle = cfg.SERIAL_WRITE_THROTTLE / 1000
        if throttle and elapsed < throttle:
            asyncio.sleep(throttle - elapsed)
   
        asyncio.run_coroutine_threadsafe(self._send_message(message), self.loop)

    async def read_message(self, timeout=5):
        return await asyncio.wait_for(self.read_queue.get(), timeout=timeout)

    def data_received(self, recv_data):
        self.last_sent_message_time = 0 # Got a message reset timer
        self.buffer += recv_data
        while len(self.buffer) >= 6:
            if checksum(self.buffer):
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("Serial -> PC {}".format(binascii.hexlify(self.buffer)))

                    self.read_queue.put_nowait(self.buffer)
                    self.buffer = b''
            else:
                self.buffer = self.buffer[1:]
        
    def connection_lost(self, exc):
        logger.error('The serial port was closed')
        self.read_queue = asyncio.Queue()
        #self.on_port_closed()

class SerialCommunication   :
    def __init__(self, port, baud=9600, timeout=5):
        self.connection = None
        self.transport = None
        self.default_timeout = timeout
        self.connection_timestamp = 0
        self.port_path = port
        self.baud = baud
        self.connected = False
        self.connected_future = None

    def on_port_closed(self):
        logger.error('Connection to panel was lost')
        self.connected_future.set_result(False)
        self.connected = False
        self.connection_timestamp = 0

    def on_port_open(self):
        logger.info('Serial port open')
        self.connected_future.set_result(True)
        self.connected = True
        self.connection_timestamp = 0

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected_future.set_result(False)
        self.connected = False

    def make_protocol(self):
        return SerialConnectionProtocol(self.on_port_open, self.on_port_closed)

    async def connect(self):
        logger.info("Connecting to serial port {}".format(self.port_path))
        loop = asyncio.get_event_loop()

        self.connected_future = loop.create_future()
        loop.call_later(5, self.open_timeout)

        self.transport, self.connection = await serial_asyncio.create_serial_connection(loop,
                                        self.make_protocol, 
                                        self.port_path, 
                                        self.baud)

        return await self.connected_future

    def write(self, data):
        """Write data to serial port"""
        if self.connected:
            self.connection.send_message(data)
        else:
            raise ConnectionError("Not connected to serial port")
        
    async def read(self, timeout=None):
        """Read data from the IP Port, if available, until the timeout is exceeded"""

        if not timeout:
            timeout = self.default_timeout

        if self.connected:
            result = await self.connection.read_message(timeout=timeout)
        else:
            raise ConnectionError("Not connected to serial port")
        
        return result

    def timeout(self, timeout=5.0):
        self.default_timeout = timeout

    def close(self):
        """Closes the serial port"""
        if self.transport:
            self.transport.close()
            self.connected = False

