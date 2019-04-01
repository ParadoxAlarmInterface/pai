# -*- coding: utf-8 -*-

import binascii
import logging
import time

import serial

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class SerialCommunication:

    def __init__(self, port, baud=9600):
        self.serialport = port
        self.baud = baud
        self.comm = None
        self.connected = False

    def connect(self, timeout=1):
        """Connects the serial port"""

        try:  # if reconnect
            if self.comm:
                self.close()
        except Exception:
            logger.exception("Cannot close Serial Port")

        logger.debug("Opening Serial port: {}".format(self.serialport))
        self.comm = serial.Serial()
        self.comm.baudrate = self.baud
        self.comm.port = self.serialport
        self.comm.timeout = timeout

        try:
            self.comm.open()
            self.connected = True
            logger.debug("Serial port open!")
            return True
        except Exception:
            logger.exception("Unable to open serial port: {}".format(self.serialport))
            return False

    def write(self, data):
        """Write data to serial port"""

        try:
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> Serial {}".format(binascii.hexlify(data)))
            self.comm.write(data)
            return True
        except Exception:
            logger.exception("Error writing to serial port")
            return False

    def read(self, sz=37, timeout=5.0):
        """Read data from the serial port, if available, until the timeout is exceeded"""
        self.comm.timeout = timeout / 5.0

        data = b""
        tstart = time.time()
        read_sz = sz

        while time.time() < (tstart + timeout):
            recv_data = self.comm.read(read_sz)

            if recv_data is None:
                continue

            data += recv_data

            if len(data) < sz:
                continue

            while not self.checksum(data) and len(data) >= 37:
                data = data[1:]

            i = 0
            while i < 37 and data[i] == 0:
                i = i + 1

            if i == 37:
                data = data[37:]
                continue

            if not self.checksum(data):
                if self.comm.in_waiting > 0:
                    read_sz = self.comm.in_waiting
                else:
                    read_sz = 1

                continue

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("Serial -> PC {}".format(binascii.hexlify(data)))
            return data

        return None

    def timeout(self, timeout=5):
        self.comm.timeout = timeout

    def close(self):
        """Closes the serial port"""
        self.comm.close()
        self.comm = None
        self.connected = False

    def flush(self):
        """Write any pending data"""
        self.comm.flush()

    def getfd(self):
        """Gets the FD associated with the serial port"""
        if self.comm.is_open:
            return self.comm.fileno()

        return None

    @staticmethod
    def checksum(data):
        """Calculates the 8bit checksum of Paradox messages"""
        c = 0

        if data is None or len(data) < 37:
            return False

        for i in data[:36]:
            c += i

        r = (c % 256) == data[36]
        return r
