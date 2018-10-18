# -*- coding: utf-8 -*-

# IP Interface

import time
import logging
import datetime
import socket
import select
from construct import Struct, Aligned, Const, Int8ub, Bytes, this, Int16ub, Int16ul, BitStruct, Default, BitsInteger, Flag, Enum
from threading import Thread, Event
import binascii
import os
from paradox_crypto import encrypt, decrypt

from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)

ip_message = Struct(
        "header" / Aligned(16,Struct(
            "sof" / Const(0xaa, Int8ub), 
            "length" / Int16ul,
            "unknown0" / Default(Int8ub, 0x01),
            "flags" / Int8ub,
            "command" / Int8ub,
            "sub_command" / Default(Int8ub, 0x00),
            'unknown1' / Default(Int8ub, 0x0a),
            'encrypt' / Default(Int8ub, 0x00),
        ), b'\xee'),
        "payload" / Aligned(16, Bytes(this.header.length), b'\xee')
      )

ip_payload_connect_response = Aligned(16, Struct(
    'command' / Const(0x00, Int8ub),
    'key'   / Bytes(16),
    'major' / Int8ub,
    'minor' / Int8ub,
    'ip_major' / Default(Int8ub, 5),
    'ip_minor' / Default(Int8ub, 2),
    'unknown'   / Default(Int8ub, 0x00)), b'\xee')


class IPInterface(Thread):
    """Interface Class using a IP Interface"""
    name = 'IPI'

    server_socket = None
    client_socket = None
    client_address = None
    alarm = None
    stop_running = Event()
    thread = None
    loop = None
    key = IP_PASSWORD
    
    def __init__(self):
        Thread.__init__(self)

    def stop(self):
        """ Stops the IP Interface Thread"""
        logger.debug("Stopping IP Interface")
        self.stop_running.set()
        logger.debug("IP Stopped")

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm
    
    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        return

    def change(self, element, label, property, value):
        """ Enqueues a change """
        return

    def notify(self, source, message, level):
        return

    def run(self):
        logger.info("Starting IP Interface")

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server_socket.bind( (IP_SOCKET_BIND_ADDRESS, IP_SOCKET_BIND_PORT))
        server_socket.listen(1)
        logger.info("IP Open")

        s_list = [server_socket]
        
        self.client_socket = None
        self.stop_running.clear()
        logger.debug("Waiting for the Alarm")

        # Wait for the alarm
        while not self.alarm and not self.stop_running.isSet():
            time.sleep(5)
        logger.info("Ready")
        while True:
            rd, wt, ex = select.select(s_list, [], s_list, 5)
            
            if self.stop_running.isSet():
                break

            for r in rd:
                if r == server_socket:
                    if self.client_socket is None:
                        self.client_socket, client_address = r.accept()
                        s_list = [server_socket, self.client_socket]
                        
                        self.alarm.pause()
                        self.client_thread = Thread(target=self.connection_watch)

                        logger.info("New client connected: {}".format(client_address))
                    else:
                        self.client_socket, client_address = r.accept()
                        self.client_socket.close()
                        logger.warn("Client connection denied")
                        self.client_socket = None

                else:
                    logging.info("Receiving data")
                    data = r.recv(1024)
                    if len(data) == 0:
                        self.handle_disconnect()
                        s_list = [server_socket]
                        break
                    else:
                        self.process_client_message(r, data)
                
    def handle_disconnect(self):
        self.key = IP_PASSWORD
        logger.info("Client disconnected")
        try:
            if self.client_socket is not None:
                self.client_socket.close()
        except:
            pass

        self.client_socket = None
        self.alarm.resume()

    def connection_watch(self):
        while self.client_socket != None:
            tstart = time.time()
            payload = self.alarm.send_wait()
            tend = time.time()
            
            if payload is not None:
                payload = encrypt(payload, self.key)
                flags = 0x39
                
                m = ip_message.build(dict(header=dict(length=len(payload), flags=flags, command=0), payload=payload))
                client.send(m)

            if tend - tstart < 0.1:
                time.sleep(0.1)

    def process_client_message(self, client, data):
        message = ip_message.parse(data)
        message_payload = data[16:]
        
        if len(message_payload) >= 16  and message.header.flags & 0x01 != 0 and len(message_payload) % 16 == 0:
            message_payload = decrypt(message_payload, self.key)[:37]

        force_plain_text = False

        if message.header.command == 0xf0:
            password = message_payload[:4]

            if password != IP_PASSWORD:
                logger.warn("Authentication Error")
                return

            # Generate a new key
            self.key = binascii.hexlify(os.urandom(8)).upper()
            
            payload = ip_payload_connect_response.build(dict(key=self.key, major=0x0, minor=32, ip_major=4, ip_minor=48))
            force_plain_text = True

        elif message.header.command == 0xf2: 
            payload = b'\x00'
        elif message.header.command == 0xf3: 
            payload = binascii.unhexlify('0100000000000000000000000000000000')
        elif message.header.command == 0xf8: 
            payload = b'\x01'
        elif message.header.command == 0x00:
            try:
                payload = self.alarm.send_wait_simple(message=message_payload[:37])
            except:
                logger.exception("Send to panel")
                return
        else:
            logger.warn("UNKNOWN: {}".format(binascii.hexlify(data)))
            return

        if payload is not None:
            flags = 0x38
            if message.header.encrypt == 0x01 and not force_plain_text:
                payload = encrypt(payload, self.key)
                flags = 0x39
           
            m = ip_message.build(dict(header=dict(length=len(payload), flags=flags, command=message.header.command), payload=payload))
            client.send(m)

