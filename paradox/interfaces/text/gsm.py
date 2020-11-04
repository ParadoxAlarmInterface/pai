# -*- coding: utf-8 -*-

import asyncio
import datetime
import json
import logging
import os
from concurrent import futures

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
        super(SerialConnectionProtocol, self).__init__(handler)
        self.buffer = b""
        self.loop = asyncio.get_event_loop()
        self.last_message = b""

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.handler.on_connection()

    async def send_message(self, message):
        self.last_message = message
        self.transport.write(message + b"\r\n")

    def data_received(self, recv_data):
        self.buffer += recv_data
        logger.debug("BUFFER: {}".format(self.buffer))
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
                self.loop.create_task(self.handler.on_message(frame))  # Callback

    def connection_lost(self, exc):
        logger.error("The serial port was closed")
        self.buffer = b""
        self.last_message = b""
        super(SerialConnectionProtocol, self).connection_lost(exc)


class SerialCommunication(ConnectionHandler):
    def __init__(self, loop, port, baud=9600, timeout=5, recv_callback=None):
        self.port_path = port
        self.baud = baud
        self.connected_future = None
        self.recv_callback = recv_callback
        self.loop = loop
        self.connected = False
        self.connection = None
        asyncio.set_event_loop(loop)
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
        logger.debug("M->I: {}".format(message))

        if self.recv_callback is not None:
            return asyncio.get_event_loop().call_soon(
                self.recv_callback(message)
            )  # Callback
        else:
            return self.queue.put_nowait(message)

    def set_recv_callback(self, callback):
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
        logger.debug("I->M: {}".format(message))
        if self.connection is not None:
            await self.connection.send_message(message)
            return await asyncio.wait_for(self.queue.get(), timeout=5, loop=self.loop)

    async def read(self, timeout=5):
        if self.connection is not None:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    async def connect(self):
        logger.info("Connecting to serial port {}".format(self.port_path))

        self.connected_future = self.loop.create_future()
        self.loop.call_later(5, self.open_timeout)

        _, self.connection = await serial_asyncio.create_serial_connection(
            self.loop, self.make_protocol, self.port_path, self.baud
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
        self.loop = asyncio.new_event_loop()
        self.message_cmt = None

    def stop(self):
        """ Stops the GSM Interface Thread"""
        self.stop_running.set()

        self.loop.stop()
        super().stop()

        logger.debug("GSM Stopped")

    def write(self, message: str, expected: str = None) -> None:
        r = b""
        while r != expected:
            r = self.loop.run_until_complete(self.port.write(message))
            data = b""

            if r == b"ERROR":
                raise Exception("Got error from modem: {}".format(r))

            while r != expected:
                r = self.loop.run_until_complete(self.port.read())
                data += r + b"\n"

    def connect(self):
        logger.info(
            "Using {} at {} baud".format(cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE)
        )
        try:
            if not os.path.exists(cfg.GSM_MODEM_PORT):
                logger.error("Modem port ({}) not found".format(cfg.GSM_MODEM_PORT))
                return False

            self.port = SerialCommunication(
                self.loop, cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE, 5
            )

        except:
            logger.exception(
                "Could not open port {} for GSM modem".format(cfg.GSM_MODEM_PORT)
            )
            return False

        self.port.set_recv_callback(None)
        result = self.loop.run_until_complete(self.port.connect())

        if not result:
            logger.exception("Could not connect to GSM modem")
            return False

        try:
            self.write(b"AT", b"OK")  # Init
            self.write(b"ATE0", b"OK")  # Disable Echo
            self.write(b"AT+CMEE=2", b"OK")  # Increase verbosity
            self.write(b"AT+CMGF=1", b"OK")  # SMS Text mode
            self.write(b"AT+CFUN=1", b"OK")  # Enable modem
            self.write(
                b"AT+CNMI=1,2,0,0,0", b"OK"
            )  # SMS received only when modem enabled, Use +CMT with SMS, No Status Report,
            self.write(b"AT+CUSD=1", b"OK")  # Enable result code presentation

        except futures.TimeoutError as e:
            logger.error("No reply from modem")
            return False

        except:
            logger.exception("Modem connect error")
            return False

        self.port.set_recv_callback(
            self.data_received
        )  # Set recv callback to handle future messages

        logger.debug("Modem connected")
        self.modem_connected = True
        return True

    def _run(self):
        super(GSMTextInterface, self)._run()

        while not self.modem_connected and not self.stop_running.isSet():
            if not self.connect():
                logger.warning("Could not connect to modem")

            self.stop_running.wait(5)

        self.loop.run_forever()

        self.stop_running.wait()

    async def data_received(self, data: str) -> bool:
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

    def handle_message(self, timestamp: str, source: str, message: str) -> None:
        """ Handle GSM message. It should be a command """

        logger.debug("Received: {} {} {}".format(timestamp, source, message))

        if source in cfg.GSM_CONTACTS:
            future = asyncio.run_coroutine_threadsafe(
                self.handle_command(message), self.alarm.work_loop
            )
            ret = future.result(10)

            m = "GSM {}: {}".format(source, ret)
            logger.info(m)
        else:
            m = "GSM {} (UNK): {}".format(source, message)
            logger.warning(m)

        self.send_message(m, EventLevel.INFO)
        ps.sendNotification(
            Notification(sender=self.name, message=m, level=EventLevel.INFO)
        )

    def send_message(self, message: str, level: EventLevel) -> None:
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            data = b'AT+CMGS="%b"\x0d%b\x1a' % (dst.encode(), message.encode())

            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.port.write(data), self.loop
                )
                result = future.result()
                logger.debug("SMS result: {}".format(result))
            except:
                logger.exception("ERROR sending SMS")

    def process_cmt(self, header: str, text: str) -> None:
        idx = header.find(" ")
        if idx <= 0:
            return

        tokens = json.loads(f"[{header[idx:]}]", strict=False)

        logger.debug("On {}, {} sent {}".format(tokens[2], tokens[0], text))
        self.handle_message(tokens[2], tokens[0], text)

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
