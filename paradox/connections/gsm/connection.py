"""GsmSerialConnection — serial transport for an AT-command GSM modem.

Unlike the panel transports, this one is a request/response command channel:
a caller writes a line and waits for the modem's reply. Unsolicited lines
(``+CMT``, ``+CUSD``) arrive at any time, so the consumer switches between
draining the queue during init and a push callback afterwards.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import serial_asyncio

from paradox.connections.connection import Connection
from paradox.connections.gsm.protocol import GsmSerialProtocol

logger = logging.getLogger("PAI").getChild(__name__)

DEFAULT_OPEN_TIMEOUT = 5
DEFAULT_COMMAND_TIMEOUT = 5


class GsmSerialConnection(Connection):
    """Serial transport for a GSM modem speaking AT commands.

    Named apart from :class:`paradox.connections.serial.connection.SerialCommunication`,
    which is the panel's binary serial transport.
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
        """Drop any unread modem output.

        Drains in place rather than replacing the queue: a coroutine already
        blocked in :meth:`read` would otherwise wait on the old object forever.
        """
        while not self.queue.empty():
            self.queue.get_nowait()

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
        """Route a modem line to the push callback, or to the waiting caller.

        The callback returns whether it consumed the line. Unsolicited results
        (``+CMT``, ``+CUSD``) belong to it; anything it declines is a reply to
        a command in flight and goes to the queue. Routing *everything* to the
        callback would starve any caller waiting on a reply for the life of
        the process.
        """
        logger.debug("M->I: %s", message)

        if self.recv_callback is not None and self.recv_callback(message):
            return

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

    def write_raw(self, message: bytes) -> None:
        """Write bytes with no line terminator, for an SMS body."""
        if self._protocol is None:
            raise ConnectionError("Not connected")

        logger.debug("I->M: %s (raw)", message)
        self._protocol.send_raw(message)

    async def read(self, timeout=DEFAULT_COMMAND_TIMEOUT, expect_prompt: bool = False):
        """Wait for the modem's next line.

        Set ``expect_prompt`` when the reply is the unterminated ``"> "`` SMS
        entry prompt rather than a line, as it is after ``AT+CMGS``. The
        expectation is dropped again on the way out: one that outlived its
        command would prime the next unterminated line to be read as a prompt.

        Callers must serialise their own exchanges -- the modem answers one
        command at a time, and the reply queue cannot tell two callers apart.
        """
        if self._protocol is None:
            return None

        if expect_prompt:
            self._protocol.expect_prompt()

        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        finally:
            if expect_prompt and self._protocol is not None:
                self._protocol.disarm_prompt()

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
            # The open itself is bounded too: open_timeout() only resolves the
            # future, which does no good if create_serial_connection is what
            # hangs -- connect() would not yet be awaiting it.
            _, self._protocol = await asyncio.wait_for(
                serial_asyncio.create_serial_connection(
                    asyncio.get_running_loop(),
                    self.make_protocol,
                    self.port_path,
                    self.baud,
                ),
                timeout=self.open_timeout_seconds,
            )

            return await self.connected_future
        except asyncio.TimeoutError:
            logger.error("Serial Port Timeout")
        except Exception:
            logger.exception("Unable to connect to GSM modem")
        finally:
            open_timeout_handler.cancel()

        return False
