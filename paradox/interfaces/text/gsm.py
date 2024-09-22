import asyncio
import json
import logging
import os
from typing import Callable, Optional

import serial_asyncio

from paradox.config import config as cfg
from paradox.connections.connection import ConnectionProtocol
from paradox.connections.handler import ConnectionHandler
from paradox.event import EventLevel, Notification
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps

# GSM interface.
# Only exposes critical status changes and accepts commands

logger = logging.getLogger("PAI").getChild(__name__)


class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, handler: ConnectionHandler):
        super().__init__(handler)
        self.last_message = b""

    async def send_message(self, message):
        self.last_message = message
        self.transport.write(message + b"\r\n")

    def data_received(self, recv_data):
        self.buffer += recv_data
        logger.debug(f"BUFFER: {self.buffer}")
        while len(self.buffer) >= 0:
            r = self.buffer.find(b"\r\n")
            # not found
            if r < 0:
                break

            # In the beginning
            if r == 0:
                self.buffer = self.buffer[2:]
                continue

            # Buffer is empty
            if len(self.buffer) == 0:
                return

            frame = self.buffer[:r]
            self.buffer = self.buffer[r:]
            # Ignore echoed bytes
            if self.last_message == frame:
                self.last_message = b""
            elif len(frame) > 0:
                self.handler.on_message(frame)  # Callback

    def connection_lost(self, exc):
        logger.error("The serial port was closed")
        self.last_message = b""
        super().connection_lost(exc)


class SerialCommunication(ConnectionHandler):
    def __init__(self, port, baud=9600, timeout=5):
        self.port_path = port
        self.baud = baud
        self.connected_future = None
        self.recv_callback = None
        self.connected = False
        self.connection = None
        self.queue = asyncio.Queue()

    def clear(self):
        self.queue = asyncio.Queue()

    def on_connection_loss(self):
        logger.error("Connection was lost")
        self.connected_future.set_result(False)
        self.connected = False

    def on_connection(self):
        logger.info("Serial port open")
        self.connected_future.set_result(True)
        self.connected = True

    def on_message(self, message: bytes):
        logger.debug(f"M->I: {message}")

        if self.recv_callback is not None:
            self.recv_callback(message)  # Callback
        else:
            self.queue.put_nowait(message)

    def set_recv_callback(self, callback: Optional[Callable[[str], bool]]):
        self.recv_callback = callback

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected_future.set_result(False)
        self.connected = False

    def make_protocol(self):
        return SerialConnectionProtocol(self)

    async def write(self, message, timeout=15):
        logger.debug(f"I->M: {message}")
        if self.connection is not None:
            await self.connection.send_message(message)
            return await asyncio.wait_for(self.queue.get(), timeout=5)

    async def read(self, timeout=5):
        if self.connection is not None:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    async def connect(self):
        logger.info(f"Connecting to serial port {self.port_path}")

        self.connected_future = asyncio.get_event_loop().create_future()
        asyncio.get_event_loop().call_later(5, self.open_timeout)

        _, self.connection = await serial_asyncio.create_serial_connection(
            asyncio.get_event_loop(), self.make_protocol, self.port_path, self.baud
        )

        return await self.connected_future


class GSMTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using GSM"""

    def __init__(self, alarm):
        super().__init__(
            alarm,
            cfg.GSM_EVENT_FILTERS,
            cfg.GSM_ALLOW_EVENTS,
            cfg.GSM_IGNORE_EVENTS,
            cfg.GSM_MIN_EVENT_LEVEL,
        )

        self.port = None
        self.modem_connected = False
        self.message_cmt = None

    def stop(self):
        """Stops the GSM Interface"""
        super().stop()
        logger.debug("GSM Stopped. TODO: Implement a proper stop")

    async def write(self, message: str, expected: str = None) -> None:
        r = b""
        while r != expected:
            r = await self.port.write(message)
            data = b""

            if r == b"ERROR":
                raise Exception(f"Got error from modem: {r}")

            while r != expected:
                r = await self.port.read()
                data += r + b"\n"

    async def connect(self):
        logger.info(f"Using {cfg.GSM_MODEM_PORT} at {cfg.GSM_MODEM_BAUDRATE} baud")
        try:
            if not os.path.exists(cfg.GSM_MODEM_PORT):
                logger.error(f"Modem port ({cfg.GSM_MODEM_PORT}) not found")
                return False

            self.port = SerialCommunication(
                cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE, 5
            )

        except Exception:
            logger.exception(f"Could not open port {cfg.GSM_MODEM_PORT} for GSM modem")
            return False

        self.port.set_recv_callback(None)
        result = await self.port.connect()

        if not result:
            logger.exception("Could not connect to GSM modem")
            return False

        try:
            await self.write(b"AT", b"OK")  # Init
            await self.write(b"ATE0", b"OK")  # Disable Echo
            await self.write(b"AT+CMEE=2", b"OK")  # Increase verbosity
            await self.write(b"AT+CMGF=1", b"OK")  # SMS Text mode
            await self.write(b"AT+CFUN=1", b"OK")  # Enable modem
            await self.write(
                b"AT+CNMI=1,2,0,0,0", b"OK"
            )  # SMS received only when modem enabled, Use +CMT with SMS, No Status Report,
            await self.write(b"AT+CUSD=1", b"OK")  # Enable result code presentation

        except asyncio.TimeoutError:
            logger.error("No reply from modem")
            return False

        except Exception:
            logger.exception("Modem connect error")
            return False

        self.port.set_recv_callback(
            self.data_received
        )  # Set recv callback to handle future messages

        logger.debug("Modem connected")
        self.modem_connected = True
        return True

    async def run(self):
        await super().run()

        while not self.modem_connected:
            if not await self.connect():
                logger.warning("Could not connect to modem")

            await asyncio.sleep(5)

    def data_received(self, data: str) -> bool:
        logger.debug(f"Data Received: {data}")

        data = data.decode()

        if data.startswith("+CMT"):
            self.message_cmt = data
        elif self.message_cmt is not None:
            self.process_cmt(self.message_cmt, data)
            self.message_cmt = None
        elif data.startswith("+CUSD:"):
            self.process_cusd(data)

        return True

    async def handle_message(self, timestamp: str, source: str, message: str) -> None:
        """Handle GSM message. It should be a command"""

        logger.debug(f"Received: {timestamp} {source} {message}")

        if source in cfg.GSM_CONTACTS:
            ret = await self.handle_command(message)

            m = f"GSM {source}: {ret}"
            logger.info(m)
        else:
            m = f"GSM {source} (UNK): {message}"
            logger.warning(m)

        self.send_message(m, EventLevel.INFO)
        ps.sendNotification(
            Notification(sender=self.name, message=m, level=EventLevel.INFO)
        )

    async def send_message(self, message: str, level: EventLevel) -> None:
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            data = b'AT+CMGS="%b"\x0d%b\x1a' % (dst.encode(), message.encode())

            try:
                result = await self.port.write(data)
                logger.debug(f"SMS result: {result}")
            except Exception:
                logger.exception("ERROR sending SMS")

    def process_cmt(self, header: str, text: str) -> None:
        idx = header.find(" ")
        if idx <= 0:
            return

        tokens = json.loads(f"[{header[idx:]}]", strict=False)

        logger.debug(f"On {tokens[2]}, {tokens[0]} sent {text}")
        asyncio.create_task(self.handle_message(tokens[2], tokens[0], text))

    def process_cusd(self, message: str) -> None:
        idx = message.find(" ")
        if idx < 0:
            return

        tokens = json.loads(f"[{message[idx:]}]", strict=False)

        code = tokens[0]
        if code == 1:
            logger.info("Modem registered into network")
            ps.sendNotification(
                Notification(
                    sender=self.name,
                    message="Modem registered into network",
                    level=EventLevel.INFO,
                )
            )
        elif code == 4:
            logger.warning("CUSD code not supported")
            return
        else:
            return
