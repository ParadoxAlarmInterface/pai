# -*- coding: utf-8 -*-

# GSM interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import Interface

import time
import logging
import datetime
import queue
import serial

from paradox.event import EventLevel
from paradox.lib.utils import SortableTuple
from config import user as cfg

class GSMInterface(Interface):
    """Interface Class using GSM"""
    name = 'gsm'

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.port = None
        self.modem_connected = False

    def stop(self):
        """ Stops the GSM Interface Thread"""
        self.logger.debug("Stopping GSM Interface")
        self.stop_running.set()

        self.port.close()

        self.logger.debug("GSM Stopped")

    def event(self, raw):
        """ Enqueues an event"""

        # Fire Alarm and Strobe
        # Special Alarms
        ignore = True
        for tag in raw.tags:
            if '_alarm' in tag:
                ignore = False
                break

        if not ignore:
            self.queue.put_nowait(SortableTuple((2, 'event', (raw))))

    def notify(self, source, message, level):
        if source == self.name:
            return

        if level.value < EventLevel.CRITICAL.value:
            return

        self.queue.put_nowait(SortableTuple(
            (2, 'notify', (source, message, level))))

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
            self.logger.exception("Modem write")
            self.modem_connected = False

        return data

    def run(self):
        self.logger.info("Starting GSM Interface")

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
                                self.notification_handler.notify(
                                    self.name, tokens[1], logging.INFO)
                    else:
                        self.run_loop()

                except Exception:
                    self.modem_connected = False
                    # self.logger.exception("")

        except (KeyboardInterrupt, SystemExit):
            self.logger.debug("GSM loop stopping")
            return

        except Exception:
            self.logger.exception("GSM loop")

    def run_loop(self):
        try:
            item = self.queue.get(block=False, timeout=1)
            if item[1] == 'change':
                self.handle_change(item[2])
            elif item[1] == 'event':
                self.handle_event(item[2])
            elif item[1] == 'notify':
                self.send_message("{}: {}".format(item[2][0], item[2][1]))

        except queue.Empty as e:
            return True
        except Exception:
            self.logger.exception("loop")

        return True

    def connected(self):
        if not self.modem_connected:
            self.logger.info("Using {} at {} baud".format(
                cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE))
            commands = [b'AT', b'ATE0', b'AT+CMGF=1',
                        b'AT+CNMI=1,2,0,0,0', b'AT+CUSD=1,"*111#"']
            try:
                self.port = serial.Serial(
                    cfg.GSM_MODEM_PORT, baudrate=cfg.GSM_MODEM_BAUDRATE, timeout=5)
                for command in commands:
                    if self.port.write(command) == 0:
                        self.logger.error("Unable to initialize modem")
                        return False
            except Exception:
                self.logger.exception("Modem connect error")
                return False

            self.modem_connected = True
            self.logger.info("Started GSM Interface")

        return True

    def send_sms(self, dst, message):
        self.write('AT+CMGS="{}"'.format(dst))
        self.write(message)
        self.write('\x1A\r\n')

    def send_message(self, message):
        if self.port is None:
            self.logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            self.send_sms(dst, message)

    def handle_message(self, timestamp, source, message):
        """ Handle GSM message. It should be a command """

        self.logger.debug("Received Message {} {} {}".format(
            timestamp, source, message))

        if self.alarm is None:
            return

        self.notification_handler.notify(
            self.name, "{}: {}".format(source, message), logging.INFO)

        if source in cfg.GSM_CONTACTS:
            ret = self.send_command(message)

            if ret:
                self.logger.info("ACCEPTED: {}".format(message))
                self.send_sms(source, "ACCEPTED: {}".format(message))
                self.notification_handler.notify(
                    self.name, "ACCEPTED: {}: {}".format(source, message), logging.INFO)
            else:
                self.logger.warning("REJECTED: {}".format(message))
                self.send_sms(source, "REJECTED: {}".format(message))
                self.notification_handler.notify(
                    self.name, "REJECTED: {}: {}".format(source, message), logging.INFO)
        else:
            self.logger.warning("REJECTED: {}".format(message))
            self.notification_handler.notify(
                self.name, "REJECTED: {}: {}".format(source, message), logging.INFO)

    def handle_event(self, raw):
        """Handle Live Event"""

        # Ignore some events
        for ev in cfg.GSM_IGNORE_EVENTS:
            if raw.major == ev[0] and (raw.minor == ev[1] or ev[1] == -1):
                return

        self.send_message(raw.message())

        for contact in cfg.GSM_CONTACTS:
            self.write('ATD{}'.format(contact))
