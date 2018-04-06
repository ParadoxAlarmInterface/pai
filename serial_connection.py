import serial
import logging
import time

class SerialCommunication:    
    def __init__(self, port, logger=logging.getLogger()):
        self.serialport = port
        self.comm = None
        self.logger = logger

    def connect(self, baud=9600, timeout=1):
        """Connects the serial port"""

        self.logger.debug( "Opening Serial port: {}".format(self.serialport))
        self.comm = serial.Serial()
        self.comm.baudrate = baud
        self.comm.port =  self.serialport
        self.comm.timeout = timeout

        try:
            self.comm.open()
            self.logger.debug( "Serial port open!")
            return True
        except:
            self.logger.exception("Error opening port {}".format(self.serialport))
            return False


    def write(self, data):
        """Write data to serial port"""

        try:
            self.comm.write(data)
            return True
        except:
            self.logger.exception("Error writing to serial port")
            return False
        
    def read(self, sz=37, timeout=5):        
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
            
            if not self.checksum(data):
                if self.comm.in_waiting > 0:
                    read_sz = self.comm.in_waiting
                else:
                    read_sz = 1
                
                continue

            return data
            
        return None


    def disconnect(self):
        """Closes the serial port"""
        self.comm.close()
        
    def flush(self):
        """Write any pending data"""
        self.comm.flush()

    def getfd(self):
        """Gets the FD associated with the serial port"""
        if self.comm.is_open:
            return self.comm.fileno()

        return None

    def checksum(self, data):
        """Calculates the 8bit checksum of Paradox messages"""
        c = 0
        
        if data is None or len(data) < 37:
            return False

        for i in data[:36]:
            c += i

        r = (c % 256) == data[36]
        return r