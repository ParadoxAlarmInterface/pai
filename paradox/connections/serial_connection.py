# -*- coding: utf-8 -*-


import logging
import typing

import serial_asyncio

from .connection import Connection
from .protocols import SerialConnectionProtocol

logger = logging.getLogger('PAI').getChild(__name__)


class SerialCommunication(Connection):
    def __init__(self, on_message: typing.Callable[[bytes], None], port, baud=9600):
        super().__init__(on_message=on_message)
        self.port_path = port
        self.baud = baud
        self.connected_future = None

    def on_port_closed(self):
        logger.error('Connection to panel was lost')
        if not self.connected_future.done():
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
        return SerialConnectionProtocol(self.on_message, self.on_port_open, self.on_port_closed)

    async def connect(self):
        logger.info("Connecting to serial port {}".format(self.port_path))

        self.connected_future = self.loop.create_future()
        self.loop.call_later(5, self.open_timeout)

        _, self.connection = await serial_asyncio.create_serial_connection(self.loop,
                                        self.make_protocol, 
                                        self.port_path, 
                                        self.baud)

        return await self.connected_future
