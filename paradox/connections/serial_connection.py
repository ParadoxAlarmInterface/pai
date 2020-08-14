# -*- coding: utf-8 -*-


import logging
import os
import stat
import typing

import serial_asyncio
from serial import SerialException

from ..exceptions import SerialConnectionOpenFailed
from .connection import Connection
from .handler import ConnectionHandler
from .protocols import SerialConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)


class SerialCommunication(Connection, ConnectionHandler):
    def __init__(self, port, baud=9600):
        super().__init__()
        self.port_path = port
        self.baud = baud
        self.connected_future = None

    def on_connection_loss(self):
        logger.error("Connection to panel was lost")
        self.connected = False
        if not self.connected_future.done():
            self.connected_future.set_result(self.connected)

    def on_connection(self):
        logger.info("Serial port open")
        self.connected = True
        if not self.connected_future.done():
            self.connected_future.set_result(self.connected)

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected = False
        self.connected_future.set_result(self.connected)

    def make_protocol(self):
        return SerialConnectionProtocol(self)

    async def connect(self) -> bool:
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
                return False

        self.connected_future = self.loop.create_future()
        open_timeout_handler = self.loop.call_later(5, self.open_timeout)

        try:
            _, self._protocol = await serial_asyncio.create_serial_connection(
                self.loop, self.make_protocol, self.port_path, self.baud
            )

            return await self.connected_future
        except SerialException as e:
            self.connected_future.cancel()
            raise SerialConnectionOpenFailed(
                "Connection to serial port failed"
            ) from e  # PAICriticalException
        except:
            logger.exception("Unable to connect to Serial")
        finally:
            open_timeout_handler.cancel()

        return False
