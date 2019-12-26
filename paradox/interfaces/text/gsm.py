# -*- coding: utf-8 -*-

import asyncio
import datetime
import logging
import os
from concurrent import futures

import serial_asyncio

from paradox.config import config as cfg
from paradox.connections.connection import ConnectionProtocol
from paradox.event import EventLevel, Notification
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps

# GSM interface.
# Only exposes critical status changes and accepts commands

logger = logging.getLogger('PAI').getChild(__name__)

INIT_COMMANDS = [b'AT',
                 b'ATE0',
                 b'AT+CMGF=1',
                 b'AT+CNMI=1,2,0,0,0',
                 b'AT+CUSD=1,"*111#"'
                 ]


class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_port_open, on_con_lost, on_recv_data):
        super(SerialConnectionProtocol, self).__init__(on_message=on_recv_data, on_con_lost=on_con_lost)
        self.buffer = b''
        self.on_port_open = on_port_open
        self.loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.on_port_open()

    async def send_message(self, message):
        self.transport.write(message + b'\r\n')

    def data_received(self, recv_data):
        self.buffer += recv_data

        while True:
            self.buffer = self.buffer.lstrip()
            r = self.buffer.find(b'\n')  # \r\n
            if r <= 0:
                break

            frame = self.buffer[:r].strip()
            self.buffer = self.buffer[r:]
            self.loop.create_task(self.on_message(frame))  # Callback

    def connection_lost(self, exc):
        logger.error('The serial port was closed')
        self.buffer = b''
        super(SerialConnectionProtocol, self).connection_lost(exc)


class SerialCommunication:
    def __init__(self, loop, port, baud=9600, timeout=5, recv_callback=None):
        self.port_path = port
        self.baud = baud
        self.connected_future = None
        self.recv_callback = recv_callback
        self.loop = loop
        self.connected = False
        asyncio.set_event_loop(loop)
        self.queue = asyncio.Queue()

    def clear(self):
        self.queue = asyncio.Queue()

    def on_port_closed(self):
        logger.error('Connection was lost')
        self.connected_future.set_result(False)
        self.connected = False

    def on_port_open(self):
        logger.info('Serial port open')
        self.connected_future.set_result(True)
        self.connected = True

    async def on_data_received(self, message):
        logger.debug("M->I: {}".format(message))

        if self.recv_callback is not None:
            self.loop.create_task(self.recv_callback(message))  # Callback
        else:
            asyncio.ensure_future(self.queue.put(message))

        if self.recv_callback is not None:
            return await self.recv_callback(message)

    def set_recv_callback(self, callback):
        self.recv_callback = callback

    def open_timeout(self):
        if self.connected_future.done():
            return

        logger.error("Serial Port Timeout")
        self.connected_future.set_result(False)
        self.connected = False

    def make_protocol(self):
        return SerialConnectionProtocol(self.on_port_open, self.on_port_closed, self.on_data_received)

    async def write(self, message):
        logger.debug("I->M: {}".format(message))
        if self.connection is not None:
            return await self.connection.send_message(message)

    async def read(self, timeout=5):
        if self.connection is not None:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)

    async def connect(self):
        logger.info("Connecting to serial port {}".format(self.port_path))

        self.connected_future = self.loop.create_future()
        self.loop.call_later(5, self.open_timeout)

        _, self.connection = await serial_asyncio.create_serial_connection(self.loop,
                                                                           self.make_protocol,
                                                                           self.port_path,
                                                                           self.baud)

        return await self.connected_future


class GSMTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using GSM"""
    name = 'gsm'

    def __init__(self):
        super().__init__(cfg.GSM_EVENT_FILTERS, cfg.GSM_ALLOW_EVENTS, cfg.GSM_IGNORE_EVENTS,
                         cfg.GSM_MIN_EVENT_LEVEL)

        self.port = None
        self.modem_connected = False
        self.loop = None
        self.loop = asyncio.new_event_loop()

    def stop(self):
        """ Stops the GSM Interface Thread"""
        logger.info("Stopping GSM Interface")
        self.stop_running.set()

        if self.port is not None:
            self.port.close()

        self.loop.stop()
        super().stop()

        logger.debug("GSM Stopped")

    def connect(self):
        logger.info("Using {} at {} baud".format(cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE))

        try:
            if not os.path.exists(cfg.GSM_MODEM_PORT):
                logger.error("Modem port ({}) not found".format(cfg.GSM_MODEM_PORT))
                return False

            self.port = SerialCommunication(self.loop, cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE, 5)

        except:
            logger.exception("Could not open port {} for GSM modem".format(cfg.GSM_MODEM_PORT))
            return False

        result = self.loop.run_until_complete(self.port.connect())

        if not result:
            logger.exception("Could not connect to GSM modem")
            return False

        try:
            for command in INIT_COMMANDS:
                self.loop.run_until_complete(self.port.write(command))
                self.loop.run_until_complete(self.port.read())

        except futures.TimeoutError as e:
            logger.error("No reply from modem")
            return False

        except Exception:
            logger.exception("Modem connect error")
            return False

        self.port.set_recv_callback(self.data_received)  # Set recv callback to handle future messages

        self.modem_connected = True
        return True

    def _run(self):
        logger.info("Starting GSM Interface")

        while not self.modem_connected and not self.stop_running.isSet():
            if not self.connect():
                logging.warning("Could not connect to modem")

            self.stop_running.wait(5)

        self.loop.run_forever()

        self.stop_running.wait()

    async def data_received(self, data):

        if len(data) == 0:
            return

        if not self.modem_connected:
            return

        logger.debug("Data received: {}".format(data))

        data = data.decode().strip()

        # Ignore this as it is a status message of a successful operation
        if data == 'OK':
            return

        # Ups... log
        if data.startswith('ERROR'):
            logger.warning("Got error from Modem: {}".format(data))
            return

        # Process message from modem
        tokens = data.split('"')
        for i in range(len(tokens)):
            tokens[i] = tokens[i].strip()

        if len(tokens) <= 0:
            return

        if tokens[0] == '+CMT:':
            source = tokens[1]
            timestamp = datetime.datetime.strptime(
                tokens[5].split('+')[0], '%y/%m/%d,%H:%M:%S')
            message = tokens[6]
            self.handle_message(timestamp, source, message)
        elif tokens[0].startswith('+CUSD:'):
            ps.sendNotification(Notification(sender=self.name, message=tokens[1], level=EventLevel.INFO))

        return True

    def handle_message(self, timestamp, source, message):
        """ Handle GSM message. It should be a command """

        logger.debug("Received message: {} {} {}".format(
            timestamp, source, message))

        if source in cfg.GSM_CONTACTS:
            ret = self.handle_command(message)

            m = "FROM {}: {}".format(source, ret)
            logger.info(m)
        else:
            m = "INVALID SENDER: {}".format(message)
            logger.warning(m)

        ps.sendNotification(Notification(sender=self.name, message=message, level=EventLevel.INFO))

    def send_message(self, message: str, level: EventLevel):
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            message = 'AT+CMGS="{}"{}\x1A'.format(dst, message)
            self.loop.run_until_complete(self.port.write(message.encode()))
