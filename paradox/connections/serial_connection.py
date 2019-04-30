# -*- coding: utf-8 -*-

import binascii
import logging
import time

import asyncio
import serial_asyncio

from paradox.config import config as cfg
from .connection import Connection, ConnectionProtocol

logger = logging.getLogger('PAI').getChild(__name__)

last = 0


def checksum(data, min_message_length):
    """Calculates the 8bit checksum of Paradox messages"""
    c = 0

    if data is None or len(data) < min_message_length:
        return False

    for i in data[:-1]:
        c += i

    r = (c % 256) == data[-1]
    return r


class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_port_open, on_port_closed, variable_message_length = True):
        super(SerialConnectionProtocol, self).__init__()
        self.buffer = b''
        self.on_port_open = on_port_open
        self.on_port_closed = on_port_closed
        self.loop = asyncio.get_event_loop()
        self.variable_message_length = variable_message_length

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.on_port_open()
 
    async def _send_message(self, message):

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> SER {}".format(binascii.hexlify(message)))

        await self.transport.write(message)

    def send_message(self, message):
        asyncio.run_coroutine_threadsafe(self._send_message(message), self.loop)

    async def read_message(self, timeout=5):
        logger.debug("read_message")
        return await asyncio.wait_for(self.read_queue.get(), timeout=timeout)

    def on_frame(self, frame):
        logger.debug("on_frame")
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("SER -> PAI {}".format(binascii.hexlify(frame)))

        self.read_queue.put_nowait(frame)

    def data_received(self, recv_data):
        self.buffer += recv_data
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("Recv: {}".format(binascii.hexlify(recv_data)))
            logger.debug("Buffer:  {}".format(binascii.hexlify(self.buffer)))

        min_length = 4 if self.variable_message_length else 37

        while len(self.buffer) >= min_length:
            if self.variable_message_length:
                if self.buffer[0] >> 4 == 0:
                    potential_packet_length = 37
                elif self.buffer[0] >> 4 in [1, 3, 4, 5, 6, 7, 8, 9]:
                    potential_packet_length = self.buffer[1] if self.buffer[1] > 0 and self.buffer[1] <= 71  else 37
                elif self.buffer[0] >> 4 in [0x0A, 0x0B, 0x0D]:
                    potential_packet_length = self.buffer[1]
                elif self.buffer[0] >> 4 == 0x0C:
                    potential_packet_length = self.buffer[1] * 256 + self.buffer[2]
                elif self.buffer[0] >> 4 == 0x0E:
                    if self.buffer[1] < 37 or self.buffer[1] == 0xFF: # MG/SP in 21st century and EVO Live Events. Probable values=0x13, 0x13, 0x00, 0xFF
                        potential_packet_length = 37
                    else:
                        potential_packet_length = self.buffer[1]
                else:
                    potential_packet_length = 37

            else:
                potential_packet_length = 37

            logger.debug("Potential Length: {}".format(potential_packet_length))

            if len(self.buffer) < potential_packet_length:
                break

            frame = self.buffer[:potential_packet_length]

            if checksum(frame, min_length):
                logger.debug("Have valid frame")
                self.buffer = self.buffer[len(frame):]  # Remove message
                self.on_frame(frame)
            else:
                logger.debug("searching")
                self.buffer = self.buffer[1:]

    def connection_lost(self, exc):
        logger.error('The serial port was closed')
        self.buffer = b''
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
        self.connection = SerialConnectionProtocol(self.on_port_open, self.on_port_closed)
        return self.connection

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

    def set_variable_message_length(self, mode):
        self.connection.variable_message_length = mode
