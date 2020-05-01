# -*- coding: utf-8 -*-


import logging
import os
import stat
import typing

import serial_asyncio
from serial import SerialException

from ..exceptions import SerialConnectionOpenFailed
from .connection import Connection
from .protocols import SerialConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)


class SerialCommunication(Connection):
    def __init__(self, on_message: typing.Callable[[bytes], None], port, baud=9600):
        super().__init__(on_message=on_message)
        self.port_path = port
        self.baud = baud
        self.connected_future = None

    def on_port_closed(self):
        logger.error("Connection to panel was lost")
        if not self.connected_future.done():
            self.connected_future.set_result(False)
        self.connected = False

    def on_port_open(self):
        logger.info("Serial port open")
        if not self.connected_future.done():
            self.connected_future.set_result(True)
        self.connected = True

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected_future.set_result(False)
        self.connected = False

    def make_protocol(self):
        return SerialConnectionProtocol(
            self.on_message, self.on_port_open, self.on_port_closed
        )

    async def connect(self):
        logger.info(f"Connecting to serial port {self.port_path}")

        if not os.access(self.port_path, mode=os.R_OK | os.W_OK):
            logger.info(f"{self.port_path} is not readable/writable. Trying to fix...")
            try:
                os.chmod(
                    self.port_path,
                    stat.S_IRUSR
                    | stat.S_IWUSR
                    | stat.S_IRGRP
                    | stat.S_IWGRP
                    | stat.S_IROTH
                    | stat.S_IWOTH,
                )
                logger.info(f"File {self.port_path} permissions changed")
            except OSError:
                logger.error(f"Failed to update file {self.port_path} permissions")

        self.connected_future = self.loop.create_future()
        self.loop.call_later(5, self.open_timeout)

        try:
            _, self._protocol = await serial_asyncio.create_serial_connection(
                self.loop, self.make_protocol, self.port_path, self.baud
            )
        except SerialException as e:
            self.connected_future.cancel()
            raise SerialConnectionOpenFailed("Connection to serial port failed") from e

        return await self.connected_future
