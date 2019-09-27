# -*- coding: utf-8 -*-

import datetime
import logging
import re
import time

import serial

from paradox.config import config as cfg
from paradox.event import EventLevel
# GSM interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)


class GSMInterface(ThreadQueueInterface):
    """Interface Class using GSM"""
    name = 'gsm'

    def __init__(self):
        super().__init__()

        self.port = None
        self.modem_connected = False

    def stop(self):
        """ Stops the GSM Interface Thread"""
        logger.debug("Stopping GSM Interface")
        self.stop_running.set()

        self.port.close()

        logger.debug("GSM Stopped")

    def write(self, message):
        data = b''

        if not self.connected():
            return data

        try:
            self.port.write((message + '\r\n').encode('latin-1'))
            time.sleep(0.1)
            while self.port.in_waiting > 0:
                data += self.port.read()

            data = data.strip().decode('latin-1')
        except Exception:
            logger.exception("Modem write")
            self.modem_connected = False

        return data

    def run(self):
        logger.info("Starting GSM Interface")

        ps.subscribe(self._handle_panel_event, "events")
        ps.subscribe(self._handle_notify, "notifications")

        try:
            while not self.stop_running.isSet():
                time.sleep(1)

                while not self.connected() and self.stop_running.isSet():
                    logging.warning("Could not connect to modem")
                    time.sleep(10)

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
                    # logger.exception("")

        except (KeyboardInterrupt, SystemExit):
            logger.debug("GSM loop stopping")
            return

        except Exception:
            logger.exception("GSM loop")

        return True

    def connected(self):
        if not self.modem_connected:
            logger.info("Using {} at {} baud".format(
                cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE))
            commands = [b'AT', b'ATE0', b'AT+CMGF=1',
                        b'AT+CNMI=1,2,0,0,0', b'AT+CUSD=1,"*111#"']
            try:
                self.port = serial.Serial(
                    cfg.GSM_MODEM_PORT, baudrate=cfg.GSM_MODEM_BAUDRATE, timeout=5)
                for command in commands:
                    if self.port.write(command) == 0:
                        logger.error("Unable to initialize modem")
                        return False
            except Exception:
                logger.exception("Modem connect error")
                return False

            self.modem_connected = True
            logger.info("Started GSM Interface")

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

        if self.alarm is None:
            return

        if source in cfg.GSM_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("ACCEPTED: {}".format(message))
                self.send_sms(source, "ACCEPTED: {}".format(message))
                message = "ACCEPTED: {}: {}".format(source, message)
            else:
                logger.warning("REJECTED: {}".format(message))
                self.send_sms(source, "REJECTED: {}".format(message))
                message = "REJECTED: {}: {}".format(source, message)
        else:
            logger.warning("REJECTED: {}".format(message))
            message = "REJECTED: {}: {}".format(source, message)

        ps.sendMessage("notifications",
                       message=dict(source=self.name,
                                    message=message,
                                    level=EventLevel.INFO))

    def _handle_notify(self, message):
        if message['level'] < EventLevel.CRITICAL:
            return

        if message['source'] != self.name:
            self.send_message(message['payload'])

    def _handle_panel_event(self, event):
        """Handle Live Event"""
        if event.level < EventLevel.CRITICAL:
            return

        major_code = event.major
        minor_code = event.minor

        # Only let some elements pass
        allow = False
        for ev in cfg.GSM_ALLOW_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = True
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = True
                    break

        # Ignore some events
        for ev in cfg.GSM_IGNORE_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = False
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = False
                    break

        if allow:
            self.send_message(event.message)
