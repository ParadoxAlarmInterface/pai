# -*- coding: utf-8 -*-

import binascii
import logging
import time

import asyncio
import serial_asyncio

from paradox.config import config as cfg
from .connection import Connection, ConnectionProtocol

logger = logging.getLogger('PAI').getChild(__name__)

MIN_MESSAGE_LEN = 6

last = 0
def checksum(data):
    """Calculates the 8bit checksum of Paradox messages"""
    c = 0

    if data is None or len(data) < MIN_MESSAGE_LEN:
        return False

    for i in data[:-1]:
        c += i

    r = (c % 256) == data[-1]
    return r

class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_port_open, on_port_closed):
        super(SerialConnectionProtocol, self).__init__()
        self.buffer = b''
        self.on_port_open = on_port_open
        self.on_port_closed = on_port_closed
        self.loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.on_port_open()
 
    async def _send_message(self, message):
        await self.transport.write(message)
        self.last_sent_message_time = time.time()

    def send_message(self, message):
        
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PC -> Serial {}".format(binascii.hexlify(message)))
        
        asyncio.run_coroutine_threadsafe(self._send_message(message), self.loop)

    async def read_message(self, timeout=5):
        return await asyncio.wait_for(self.read_queue.get(), timeout=timeout)

    def data_received(self, recv_data):
        self.buffer += recv_data
    
        while len(self.buffer) >= MIN_MESSAGE_LEN:
            logger.debug(len(self.buffer))
            if self.buffer[0] >> 4 == 1 and checksum(self.buffer[:MIN_MESSAGE_LEN]):
                # We have received EVO192 Successful connection response: 120600000018 (6 bytes)
                frame = self.buffer[:MIN_MESSAGE_LEN]
            elif len(self.buffer) >= 37:
                if checksum(self.buffer[:37]):
                    frame = self.buffer[:37]
                else:
                    self.buffer = self.buffer[1:]
                    continue
            else:
                break

            self.buffer = self.buffer[len(frame):] # Remove message

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("Serial -> PC {}".format(binascii.hexlify(frame)))
               
            self.read_queue.put_nowait(frame)

    def connection_lost(self, exc):
        logger.error('The serial port was closed')
        super(SerialConnectionProtocol, self).connection_lost(exc)

class SerialCommunication(Connection):
    def __init__(self, port, baud=9600, timeout=5):
        super(SerialCommunication, self).__init__(timeout=timeout)
        self.port_path = port
        self.baud = baud
        self.connected_future = None

    def on_port_closed(self):
        logger.error('Connection to panel was lost')
        self.connected_future.set_result(False)
        self.connected = False

    def on_port_open(self):
        logger.info('Serial port open')
        self.connected_future.set_result(True)
        self.connected = True

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

        _, self.connection = await serial_asyncio.create_serial_connection(loop,
                                        self.make_protocol, 
                                        self.port_path, 
                                        self.baud)

        return await self.connected_future
