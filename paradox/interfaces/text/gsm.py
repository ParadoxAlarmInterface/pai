# -*- coding: utf-8 -*-

import datetime
import logging
import time
from concurrent import futures

from paradox.event import EventLevel
# GSM interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces.text.core import AbstractTextInterface
import asyncio
import serial_asyncio

from paradox.config import config as cfg
from paradox.connections.connection import Connection, ConnectionProtocol
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)

class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_port_open, on_con_lost):
        super(SerialConnectionProtocol, self).__init__(on_con_lost=on_con_lost)
        self.buffer = b''
        self.on_port_open = on_port_open
        self.loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.on_port_open()

    async def _send_message(self, message):
        logger.debug("I->M: {}".format(message))
        await self.transport.write(message)

    def send_message(self, message):
        asyncio.run_coroutine_threadsafe(self._send_message(message), self.loop)

    async def read_message(self, timeout=5):
        return await asyncio.wait_for(self.read_queue.get(), timeout=timeout)

    def data_received(self, recv_data):
        logger.debug("M->I: Data: {}".format(recv_data))
        self.buffer += recv_data
        r = self.buffer.find(b'\r\n')
        if r > 0:
            frame = self.buffer[:r]
            self.buffer[r:]
            logger.debug("M->I: Frame: {}".format(frame))
            self.read_queue.put_nowait(frame)

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
        logger.error('Connection was lost')
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


class GSMTextInterface(AbstractTextInterface):
    """Interface Class using GSM"""
    name = 'gsm'

    def __init__(self):
        super().__init__(cfg.GSM_ALLOW_EVENTS, cfg.GSM_IGNORE_EVENTS)

        self.port = None
        self.modem_connected = False
        self.loop = None
        self.loop = asyncio.get_event_loop()

    def stop(self):
        """ Stops the GSM Interface Thread"""
        logger.debug("Stopping GSM Interface")
        self.stop_running.set()

        if self.port is not None:
            self.port.close()

        super().stop()
        logger.debug("GSM Stopped")

    def connect(self):
        logger.info("Using {} at {} baud".format(
            cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE))

        commands = [b'AT', b'ATE0', b'AT+CMGF=1',
                    b'AT+CNMI=1,2,0,0,0', b'AT+CUSD=1,"*111#"']
        try:
            self.port = SerialCommunication(cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE)
        except:
            logger.exception("Could not open port")
            return False


            result = self.loop.run_until_complete(self.port.connect())

            if not result:
                logger.error("Could not open modem port")
                return False

            for command in commands:
                if self.port.write(command) == 0:
                    logger.error("Unable to initialize modem")
                    return False
                else:
                    message = self.loop.run_until_complete(self.port.read())
                    logger.info(message)
        except futures.TimeoutError as e:
            logger.error("No reply from modem")
            return False
        except Exception:
            logger.exception("Modem connect error")
            return False

        self.modem_connected = True
        return True









    def write(self, message):
        if not self.connected():
            return None

        try:
            logger.debug("I->M: {}".format(message))
            self.port.write((message + '\r\n').encode('latin-1'))

            data = self.port.read_message()
            data = data.strip().decode('latin-1')
            logger.debug("M->I: {}".format(data))
            return data

        except Exception:
            logger.exception("Modem write")
            self.modem_connected = False

        return None

    def _run(self):
        logger.info("Starting GSM Interface")

        while not self.stop_running.isSet():
            while not self.modem_connected:
                if not self.connect():
                    logging.warning("Could not connect to modem")

                time.sleep(5)
                continue

    def handle_message(self, message):
            try:
                data = self.port.read(200)

                if len(data) > 0:
                    tokens = data.decode('latin-1').strip().split('"')
                    for i in range(len(tokens)):
                        tokens[i] = tokens[i].strip()

                    if len(tokens) > 0:
                        if tokens[0] == '+CMT:':
                            source = tokens[1]
                            timestamp = datetime.datetime.strptime(
                                tokens[5].split('+')[0], '%y/%m/%d,%H:%M:%S')
                            message = tokens[6]
                            self.handle_message(timestamp, source, message)
                        elif tokens[0].startswith('+CUSD:'):
                            ps.sendMessage("notifications",
                                           message=dict(source=self.name,
                                                        message=tokens[1],
                                                        level=logging.INFO))
                else:
                    self.run_loop()

            except Exception:
                self.modem_connected = False
                logger.exception("")

        return True



    def send_sms(self, dst, message):
        self.write('AT+CMGS="{}"'.format(dst))
        self.write(message)
        self.write('\x1A\r\n')

    def send_message(self, message):
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            self.send_sms(dst, message)

    def handle_message(self, timestamp, source, message):
        """ Handle GSM message. It should be a command """

        logger.debug("Received Message {} {} {}".format(
            timestamp, source, message))

        if source in cfg.GSM_CONTACTS:
            ret = self.send_command(message)

            m = "FROM {}: {}".format(source, ret)
            logger.info(m)
        else:
            m = "INVALID SENDER: {}".format(message)
            logger.warning(m)

        ps.sendMessage("notifications",
                       message=dict(source=self.name,
                                    payload=message,
                                    level=EventLevel.INFO))
