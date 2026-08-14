"""GsmSerialConnection — serial transport for an AT-command GSM modem.

Unlike the panel transports, this one is a request/response command channel:
``send_command()`` writes a line and waits for the modem's reply. Unsolicited
lines (``+CMT``, ``+CUSD``) arrive at any time, so the consumer switches
between draining the queue during init and a push callback afterwards.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import serial_asyncio

from paradox.connections.connection import Connection
from paradox.connections.gsm.protocol import GsmSerialProtocol

logger = logging.getLogger("PAI").getChild(__name__)

#: Seconds to wait for the serial port to open before giving up.
DEFAULT_OPEN_TIMEOUT = 5

#: Seconds to wait for the modem to answer a command.
DEFAULT_COMMAND_TIMEOUT = 5


class GsmSerialConnection(Connection):
    """Serial transport for a GSM modem speaking AT commands.

    Named apart from :class:`paradox.connections.serial.connection.SerialCommunication`,
    which is the panel's binary serial transport: the two share a medium and
    nothing else.
    """

    def __init__(self, port, baud=9600, timeout=DEFAULT_OPEN_TIMEOUT):
        super().__init__()
        self.port_path = port
        self.baud = baud
        self.open_timeout_seconds = timeout
        self.connected_future = None
        self.recv_callback = None
        self.queue = asyncio.Queue()

    def clear(self):
        self.queue = asyncio.Queue()

    def on_connection_loss(self):
        logger.error("Connection was lost")
        self.connected = False
        # A drop after a successful connect finds the future already resolved.
        if self.connected_future is not None and not self.connected_future.done():
            self.connected_future.set_result(False)

    def on_connection(self):
        logger.info("Serial port open")
        self.connected = True
        if not self.connected_future.done():
            self.connected_future.set_result(True)

    def on_message(self, message: bytes):
        """Route a modem line to the waiting caller or to the push callback.

        Overrides :class:`~paradox.connections.connection.Connection`, whose
        handler registry dispatches parsed panel messages. Modem lines are
        plain bytes answering a specific command, so they queue instead.
        """
        logger.debug("M->I: %s", message)

        if self.recv_callback is not None:
            self.recv_callback(message)
        else:
            self.queue.put_nowait(message)

    def set_recv_callback(self, callback: Optional[Callable[[bytes], bool]]):
        self.recv_callback = callback

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected = False
        self.connected_future.set_result(False)

    def make_protocol(self):
        return GsmSerialProtocol(self)

    def write(self, data: bytes):
        """Unsupported: the modem channel is request/response.

        ``Connection.write`` is a synchronous fire-and-forget that would leave
        :meth:`GsmSerialProtocol.send_message`'s coroutine un-awaited.
        """
        raise NotImplementedError("Use send_command() for the modem channel")

    async def send_command(self, message: bytes, timeout=DEFAULT_COMMAND_TIMEOUT):
        """Send an AT command and wait for the modem's next line."""
        if self._protocol is None:
            return None

        logger.debug("I->M: %s", message)
        await self._protocol.send_message(message)
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    async def read(self, timeout=DEFAULT_COMMAND_TIMEOUT):
        if self._protocol is None:
            return None

        return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    async def connect(self) -> bool:
        logger.info(f"Connecting to serial port {self.port_path}")

        if not os.access(self.port_path, mode=os.R_OK | os.W_OK):
            logger.error(f"{self.port_path} is not readable/writable.")
            return False

        self.connected_future = asyncio.get_running_loop().create_future()
        open_timeout_handler = asyncio.get_running_loop().call_later(
            self.open_timeout_seconds, self.open_timeout
        )

        try:
            _, self._protocol = await serial_asyncio.create_serial_connection(
                asyncio.get_running_loop(),
                self.make_protocol,
                self.port_path,
                self.baud,
            )

            return await self.connected_future
        except Exception:
            logger.exception("Unable to connect to GSM modem")
        finally:
            open_timeout_handler.cancel()

        return False
