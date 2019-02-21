# -*- coding: utf-8 -*-

# IP Interface

import time
import logging
import socket
import select
from construct import GreedyBytes, Struct, Aligned, Const, Int8ub, Bytes, this, Int16ub, Int16ul, BitStruct, Default, BitsInteger, Flag, Enum
from threading import Thread, Event
import binascii
import os
from paradox.lib.crypto import encrypt, decrypt
from paradox.interfaces import Interface

from paradox.config import config as cfg

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
        "payload" / Aligned(16, GreedyBytes, b'\xee'))

ip_payload_connect_response = Aligned(16, Struct(
    'command' / Const(0x00, Int8ub),
    'key' / Bytes(16),
    'major' / Int8ub,
    'minor' / Int8ub,
    'ip_major' / Default(Int8ub, 5),
    'ip_minor' / Default(Int8ub, 2),
    'unknown' / Default(Int8ub, 0x00)), b'\xee')


class IPInterface(Interface):
    """Interface Class using a IP Interface"""
    name = 'IPI'

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.stop_running = Event()
        self.key = cfg.IP_INTERFACE_PASSWORD

    def stop(self):
        """ Stops the IP Interface Thread"""
        self.logger.debug("Stopping IP Interface")
        self.stop_running.set()
        self.logger.debug("IP Stopped")

    def run(self):
        self.logger.info("Starting IP Interface")

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server_socket.bind((cfg.IP_INTERFACE_BIND_ADDRESS, cfg.IP_INTERFACE_BIND_PORT))
        server_socket.listen(1)
        self.logger.info("IP Open")

        s_list = [server_socket]

        self.client_socket = None
        self.stop_running.clear()
        self.logger.debug("Waiting for the Alarm")

        # Wait for the alarm
        while not self.alarm and not self.stop_running.isSet():
            time.sleep(5)
        self.logger.info("Ready")
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

                        self.logger.info("New client connected: {}".format(client_address))
                    else:
                        self.client_socket, client_address = r.accept()
                        self.client_socket.close()
                        self.logger.warn("Client connection denied")
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
        self.key = cfg.IP_INTERFACE_PASSWORD
        self.logger.info("Client disconnected")
        try:
            if self.client_socket is not None:
                self.client_socket.close()
        except Exception:
            pass

        self.client_socket = None
        self.alarm.resume()

    def connection_watch(self):
        while self.client_socket is None:
            tstart = time.time()
            payload = self.alarm.send_wait()
            tend = time.time()
            payload_len = len(payload)
            if payload is not None:
                payload = encrypt(payload, self.key)
                flags = 0x73

                m = ip_message.build(dict(header=dict(length=payload_len, unknown0=2, flags=flags, command=0), payload=payload))
                self.logger.debug("IP -> AP: {}".format(binascii.hexlify(m)))
                self.client_socket.send(m)

            if tend - tstart < 0.1:
                time.sleep(0.1)

    def process_client_message(self, client, data):
        message = ip_message.parse(data)
        message_payload = data[16:]
        self.logger.debug("AP -> IP: {}".format(binascii.hexlify(data)))
        if len(message_payload) >= 16  and message.header.flags & 0x01 != 0 and len(message_payload) % 16 == 0:
            message_payload = decrypt(message_payload, self.key)[:37]

        force_plain_text = False
        response_code = 0x01
        if message.header.command == 0xf0:
            password = message_payload[:4]

            if password != cfg.IP_INTERFACE_PASSWORD:
                self.logger.warn("Authentication Error")
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
            response_code = 0x02
            try:
                payload = self.alarm.send_wait_simple(message=message_payload[:37])
            except Exception:
                self.logger.exception("Send to panel")
                return
        else:
            self.logger.warn("UNKNOWN: {}".format(binascii.hexlify(data)))
            return

        if payload is not None:
            flags = 0x38
            payload_length = len(payload)

            if message.header.flags & 0x01 != 0 and not force_plain_text:
                payload = encrypt(payload, self.key)

                if message.header.command == 0x00:
                    flags = 0x73
                else:
                    flags = 0x39

            m = ip_message.build(dict(header=dict(length=payload_length, unknown0=response_code, flags=flags, command=message.header.command), payload=payload))
            self.logger.debug("IP -> AP: {}".format(binascii.hexlify(m)))
            client.send(m)
