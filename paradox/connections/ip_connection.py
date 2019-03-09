# -*- coding: utf-8 -*-

import socket
import logging
import time
from paradox.lib.crypto import encrypt, decrypt
from paradox.parsers.paradox_ip_messages import *
from paradox.lib import stun
import binascii
import json
import requests

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class IPConnection:
    def __init__(self, host='127.0.0.1', port=10000, password=None, timeout=5):
        self.socket = None
        self.socket_timeout = int(timeout)
        self.password = password
        self.key = password
        self.connected = False
        self.host = host
        self.port = port
        self.site_info = None
        self.module = None
        self.connection_timestamp = 0

    def connect(self):
        try: # if reconnect
            if self.socket:
                self.close()
        except Exception:
            pass

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.socket.bind(('0.0.0.0', 0))

        tries = 1
        max_tries = 3

        while tries <= max_tries:

            if cfg.IP_CONNECTION_SITEID is not None and cfg.IP_CONNECTION_EMAIL is not None:
                try:
                    r = self.connect_to_site()

                    if r and self.site_info is not None:
                        if self.connect_to_panel():
                            return True
                except Exception:
                    logger.exception('Try %d/%d. Unable to connect to SITE ID' % (tries, max_tries))
            else:
                try:
                    self.socket.settimeout(self.socket_timeout)
                    self.socket.connect((self.host, self.port))

                    if self.connect_to_panel():
                        return True
                except Exception:
                    logger.exception("Try %d/%d. Unable to connect to IP Module" % (tries, max_tries))

            tries += 1

        return False

    def connect_to_site(self):
        logger.info("Connecting to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        if self.site_info is None:
            self.site_info = self.get_site_info(siteid=cfg.IP_CONNECTION_SITEID, email=cfg.IP_CONNECTION_EMAIL)

            if self.site_info is None:
                logger.error("Unable to get site info")
                return False
            
            logger.debug("Site Info: {}".format(json.dumps(self.site_info, indent=4)))
            
            if cfg.IP_CONNECTION_PANEL_SERIAL is not None:
                for site in self.site_info['site']:
                    for module in site:
                        logger.debug("Found module with panel serial: {}".format(module['panelSerial']))
                        if module['panelSerial'] == cfg.IP_CONNECTION_PANEL_SERIAL:
                            self.module = module
                            break

                    if self.module is not None:
                        break
            else:
                self.module = self.site_info[0]['module']

            if self.module is None:
                self.site_info = None  # Reset state
                logger.error("Unable to find module with desired panel serial")
                return False
        try:
            xoraddr = binascii.unhexlify(self.module['xoraddr'])

            stun_host = 'turn.paradoxmyhome.com'

            logger.debug("STUN TCP Change Request")
            self.client = stun.StunClient(stun_host)
            self.client.send_tcp_change_request()
            stun_r = self.client.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            logger.debug("STUN TCP Binding Request")
            self.client.send_binding_request()
            stun_r = self.client.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            logger.debug("STUN Connect Request")
            self.client.send_connect_request(xoraddr=xoraddr)
            stun_r = self.client.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            self.connection_timestamp = time.time()

            connection_id = stun_r[0]['attr_body']
            raddr = self.client.sock.getpeername()

            logger.debug("STUN Connection Bind Request")
            self.client1 = stun.StunClient(host=raddr[0], port=raddr[1])
            self.client1.send_connection_bind_request(binascii.unhexlify(connection_id))
            stun_r = self.client1.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            self.socket = self.client1.sock
            logger.info("Connected to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        except Exception:
            logger.exception("Unable to negotiate connection to site")

        return True

    def connect_to_panel(self):
        try:
            logger.debug("Authenticating with IP Module")

            self.key = self.password  # first request is with initial password, next with generated by panel key
            payload = encrypt(self.key, self.key)

            msg = ip_message.build(dict(header=dict(length=len(self.key), unknown0=0x03, flags=0x09, command=0xf0, unknown1=0, encrypt=1), payload=payload))
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> IP {}".format(binascii.hexlify(msg)))

            self.socket.send(msg)
            data = self.socket.recv(1024)
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IP -> PC {}".format(binascii.hexlify(data)))

            message, message_payload = self.get_message_payload(data)

            response = ip_payload_connect_response.parse(message_payload)

            if response.login_status != 'success':
                logger.error("Error connecting to IP Module. Wrong IP Module password?")
                return False

            logger.info("Authentication Success. Panel version {:02x}, firmware: {}.{}, serial: {}".format(response.hardware_version,
                        response.ip_firmware_major,
                        response.ip_firmware_minor,
                        binascii.hexlify(response.ip_module_serial).decode('utf-8')))

            self.key = response.key

            # F2
            logger.debug("Sending F2")
            msg = ip_message.build(dict(header=dict(length=0, unknown0=0x03, flags=0x09, command=0xf2, unknown1=0, encrypt=1), payload=encrypt(b'', self.key)))
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> IP {}".format(binascii.hexlify(msg)))

            self.socket.send(msg)
            data = self.socket.recv(1024)
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IP -> PC {}".format(binascii.hexlify(data)))

            message, message_payload = self.get_message_payload(data)
            logger.debug("F2 answer: {}".format(binascii.hexlify(message_payload)))

            # F3
            logger.debug("Sending F3")
            msg = ip_message.build(dict(header=dict(length=0, unknown0=0x03, flags=0x09, command=0xf3, unknown1=0, encrypt=1), payload=encrypt(b'', self.key)))
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> IP {}".format(binascii.hexlify(msg)))

            self.socket.send(msg)
            data = self.socket.recv(1024)
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IP -> PC {}".format(binascii.hexlify(data)))

            message, message_payload = self.get_message_payload(data)

            logger.debug("F3 answer: {}".format(binascii.hexlify(message_payload)))

            # F8
            logger.debug("Sending F8")
            payload = binascii.unhexlify('0a500080000000000000000000000000000000000000000000000000000000000000000000d0')
            payload_len = len(payload)
            payload = encrypt(payload, self.key)
            msg = ip_message.build(dict(header=dict(length=payload_len, unknown0=0x03, flags=0x09, command=0xf8, unknown1=0, encrypt=1), payload=payload))

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> IP {}".format(binascii.hexlify(msg)))

            self.socket.send(msg)
            data = self.socket.recv(1024)
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IP -> PC {}".format(binascii.hexlify(data)))

            message, message_payload = self.get_message_payload(data)
            logger.debug("F8 answer: {}".format(binascii.hexlify(message_payload)))


            logger.info("Session Established with IP Module")

            self.connected = True
        except Exception:
            self.connected = False
            logger.exception("Unable to establish session with IP Module")

        return self.connected

    def write(self, data):
        """Write data to socket"""

        if not self.refresh_stun():
            return False

        try:
            if self.connected:
                payload = encrypt(data, self.key)
                msg = ip_message.build(dict(header=dict(length=len(data), unknown0=0x04, flags=0x09, command=0x00, encrypt=1), payload=payload))
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("PC -> IP {}".format(binascii.hexlify(msg)))
                self.socket.send(msg)
                return True
            else:
                return False
        except Exception:
            logger.exception("Error writing to socket.")
            raise ConnectionError()

    def read(self, sz=37, timeout=5):
        """Read data from the IP Port, if available, until the timeout is exceeded"""

        if not self.refresh_stun():
            return False

        self.socket.settimeout(timeout)
        data = b""

        while True:
            try:
                recv_data = self.socket.recv(1024)
                if recv_data == b'': # Socket was closed. Restart the connection.
                    logger.info('Connection to IP module lost.')
                    raise ConnectionResetError()
            except socket.timeout:
                return None
            except socket.error:
                logger.exception("Error reading from socket.")
                raise ConnectionError()

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

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IP -> PC {}".format(binascii.hexlify(data)))

            message, payload = self.get_message_payload(data)
            return payload

    def timeout(self, timeout=5):
        self.socket_timeout = timeout

    def close(self):
        """Closes the serial port"""

        if self.socket:
            self.socket.close()
            self.socket = None

        self.connected = False

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

    @staticmethod
    def get_site_info(email, siteid):

        logger.debug("Getting site info")
        URL = "https://api.insightgoldatpmh.com/v1/site"

        headers={'User-Agent': 'Mozilla/3.0 (compatible; Indy Library)', 'Accept-Encoding': 'identity', 'Accept': 'text/html, */*'}

        tries = 5
        while tries > 0:
            req = requests.get(URL, headers=headers, params={'email': email, 'name': siteid})
            if req.status_code == 200:
                return req.json()

            logger.warn("Unable to get site info. Retrying...")
            tries -= 1
            time.sleep(5)

        return None

    def refresh_stun(self):
        if self.site_info is None:
            return True

        try:
            # Refresh session if required
            if time.time() - self.connection_timestamp >= 500:
                logger.debug("Refreshing session")
                self.client.send_refresh_request()
                stun_r = self.client.receive_response()
                if stun.is_error(stun_r):
                    logger.error(stun.get_error(stun_r))
                    self.connected = False
                    return False

                self.connection_timestamp = time.time()

            return True
        except Exception:
            logger.exception("Session refresh")
            return False
