import serial
import logging
import time

logger = logging.getLogger('PAI').getChild(__name__)

class SerialCommunication:    
    def __init__(self, port):
        self.serialport = port
        self.comm = None

    def connect(self, baud=9600, timeout=1):
        """Connects the serial port"""

        logger.debug( "Opening Serial port: {}".format(self.serialport))
        self.comm = serial.Serial()
        self.comm.baudrate = baud
        self.comm.port =  self.serialport
        self.comm.timeout = timeout

        try:
            self.comm.open()
            logger.debug( "Serial port open!")
            return True
        except Exception as e:
            logger.error(e)
            return False

    def write(self, data):
        """Write data to serial port"""

        try:
            self.comm.write(data)
            return True
        except:
            logger.exception("Error writing to serial port")
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
            
            i = 0
            while i < 37 and data[i] == 0:
                i= i+1
            
            if i == 37:
                data= data[37:]
                continue

            if not self.checksum(data):
                if self.comm.in_waiting > 0:
                    read_sz = self.comm.in_waiting
                else:
                    read_sz = 1
                
                continue

            return data
            
        return None
    
    def timeout(self, timeout=5):
        self.comm.timeout=timeout

    def close(self):
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
