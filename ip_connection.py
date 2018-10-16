# -*- coding: utf-8 -*-

import socket
import logging
import time
from paradox_crypto import encrypt, decrypt
from paradox_ip_messages import *
import binascii

from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)

class IPConnection:
    def __init__(self, host='127.0.0.1', port=10000, password='0000', timeout=5):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind( ('0.0.0.0', 0))
        self.socket_timeout = int(timeout)
        self.key = password
        self.connected = False
        self.host = host
        self.port = port

    def connect(self):

        logger.debug( "Connecting to IP Panel at : {}".format(self.host))
        
        try:
            self.socket.settimeout(self.socket_timeout)
            self.socket.connect( (self.host, self.port) )
            
            logger.debug("IP Connection established")

            payload = encrypt(self.key, self.key)

            msg = ip_message.build(dict(header=dict(length=len(self.key), flags=0x09, command=0xf0, encrypt=1), payload=payload))
            self.socket.send(msg)
            data = self.socket.recv(1024)

            message, message_payload = self.get_message_payload(data)
            response = ip_payload_connect_response.parse(message_payload)
            self.key = response.key
            logger.debug("Set new Key to {}".format(self.key))

            logger.info("Connected to Panel with Versions {}.{} - {}.{}".format(response.major, response.minor, response.ip_major, response.ip_minor))
            
            #F2
            msg = ip_message.build(dict(header=dict(length=0, flags=0x09, command=0xf2, encrypt=1), payload=encrypt(b'', self.key)))
            self.socket.send(msg)

            data = self.socket.recv(1024)
            message, message_payload = self.get_message_payload(data)
            logger.debug("F2 answer: {}".format(binascii.hexlify(message_payload)))

            #F3
            msg = ip_message.build(dict(header=dict(length=0, flags=0x09, command=0xf3, encrypt=1), payload=encrypt(b'', self.key)))
            self.socket.send(msg)
            data = self.socket.recv(1024)
            message, message_payload = self.get_message_payload(data)
            
            logger.debug("F3 answer: {}".format(binascii.hexlify(message_payload)))
           
            #F8
            payload = binascii.unhexlify('0a500080000000000000000000000000000000000000000000000000000000000000000000d0')
            payload_len = len(payload)
            payload = encrypt(payload, self.key)
            msg = ip_message.build(dict(header=dict(length=payload_len, flags=0x09, command=0xf3, encrypt=1), payload=payload))
            self.socket.send(msg)
            data = self.socket.recv(1024)
            
            message, message_payload = self.get_message_payload(data)            
            logger.debug("F8 answer: {}".format(binascii.hexlify(message_payload)))
            
            
            logger.info("Connection fully established")

            self.connected = True
        except Exception as e:
            self.connected = False
            logger.exception("Unable to connect to IP Module")

        return self.connected

    def write(self, data):
        """Write data to socket"""

        try:
            if self.connected:
                payload = encrypt(data, self.key)
                msg = ip_message.build(dict(header=dict(length=len(data), flags=0x09, command=0x00, encrypt=1), payload=payload))
                self.socket.send(msg)
                return True
            else:
                return False
        except:
            logger.exception("Error writing to socket")
            self.connected = False
            return False
        
    def read(self, sz=37, timeout=5):        
        """Read data from the IP Port, if available, until the timeout is exceeded"""
        self.socket.settimeout(timeout)
        data = b""
        read_sz = sz

        while True: 
            try:
                recv_data = self.socket.recv(1024)
            except:
                return None

            if recv_data is None or len(recv_data) == 0:
                continue

            data += recv_data
            
            if data[0] != 0xaa:
                data = b''
                continue

            if len(recv_data) + 16 < data[1]:
                continue

            if len(data) % 16 != 0:
                continue

            message, payload = self.get_message_payload(data)
            return payload
            
        return None
    
    def timeout(self, timeout=5):
        self.socket_timeout = timeout

    def close(self):
        """Closes the serial port"""
        if self.connected:
            self.connected = False
            self.socket.close()

    def flush(self):
        """Write any pending data"""
        self.socket.flush()

    def getfd(self):
        """Gets the FD associated with the socket"""
        if self.connected:
            return self.socket.fileno()

        return None

    def get_message_payload(self, data):
        message = ip_message.parse(data)
    

        if len(message.payload) >= 16 and len(message.payload) % 16 == 0 and message.header.flags & 0x01 != 0:
            message_payload = decrypt(data[16:], self.key)[:message.header.length]
        else:
            message_payload = message.payload

        return message, message_payload
