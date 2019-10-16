# -*- coding: utf-8 -*-

import asyncio
import binascii
import json
import logging
import time
import typing

import requests

from paradox.config import config as cfg
from paradox.lib import stun
from paradox.lib.crypto import encrypt, decrypt
from paradox.parsers.paradox_ip_messages import *
from .connection import Connection, ConnectionProtocol

logger = logging.getLogger('PAI').getChild(__name__)


class IPConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_message: typing.Callable[[bytes], None], on_con_lost, key):
        super(IPConnectionProtocol, self).__init__(on_message=on_message, on_con_lost=on_con_lost)
        self.buffer = b''
        self.key = key

    def send_raw(self, raw):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> Mod {}".format(binascii.hexlify(raw)))
        self.transport.write(raw)

    def send_message(self, message):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> IPC {}".format(binascii.hexlify(message)))

        payload = encrypt(message, self.key)
        msg = ip_message.build(
            dict(header=dict(length=len(message), unknown0=0x04, flags=0x09, command=0x00, encrypt=1), payload=payload))
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("IPC -> Mod {}".format(binascii.hexlify(msg)))
        self.transport.write(msg)

    def _get_message_payload(self, data):
        message = ip_message.parse(data)

        if len(message.payload) >= 16 and len(message.payload) % 16 == 0 and message.header.flags & 0x01 != 0:
            message_payload = decrypt(data[16:], self.key)[:message.header.length]
        else:
            message_payload = message.payload[:message.header.length]

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("IPC -> PAI {}".format(binascii.hexlify(message_payload)))

        return message_payload

    def data_received(self, recv_data):
        self.buffer += recv_data

        if self.buffer[0] != 0xaa:
            if len(self.buffer) > 0:
                logger.warning('Dangling data in the receive buffer: %s' % binascii.hexlify(self.buffer))
            self.buffer = b''
            return

        if len(recv_data) + 16 < self.buffer[1]:
            return

        if len(self.buffer) % 16 != 0:
            return

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("Mod -> IPC {}".format(binascii.hexlify(self.buffer)))

        self.on_message(self._get_message_payload(self.buffer))
        self.buffer = b''


class IPConnection(Connection):
    def __init__(self, on_message: typing.Callable[[bytes], None], host='127.0.0.1', port=10000, password=None):
        super(IPConnection, self).__init__(on_message=on_message)
        self.password = password
        self.key = password
        self.host = host
        self.port = port
        self.site_info = None
        self.module = None
        self.connection_timestamp = 0

        self.stun_control = None
        self.stun_tunnel = None
        self.connection = None

    def on_connection_lost(self):
        logger.error('Connection to panel was lost')
        self.close()

    def close(self):
        logger.info('Closing IP Connection')

        self.connected = False
        self.connection_timestamp = 0
        
        if self.stun_control:
            try:
                self.stun_control.close()
                self.stun_control = None
            except Exception as e:
               logger.exception("stun_control socket close failed")
        if self.stun_tunnel:
            try:
                self.stun_tunnel.close()
                self.stun_tunnel = None
            except Exception as e:
               logger.exception("stun_control socket close failed")
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
               logger.exception("connection socket close failed")
            self.connection = None

    def make_protocol(self):
        return IPConnectionProtocol(self.on_message, self.on_connection_lost, self.key)

    async def connect(self):
        loop = asyncio.get_event_loop()
        tries = 1
        max_tries = 3

        while tries <= max_tries:

            if cfg.IP_CONNECTION_SITEID is not None and cfg.IP_CONNECTION_EMAIL is not None:
                try:
                    r = await self.connect_to_site()

                    if r and self.site_info is not None:
                        if await self.connect_to_module():
                            return True
                except Exception:
                    logger.exception('Try %d/%d. Unable to connect to SITE ID' % (tries, max_tries))
            else:
                try:
                    logger.info("Connecting to IP module. Try %d/%d"% (tries, max_tries))

                    _, self.connection = await loop.create_connection(self.make_protocol,
                                                                                   host=self.host, port=self.port)
                    if cfg.IP_CONNECTION_BARE:
                        return True

                    if await self.connect_to_module():
                        return True
                except OSError as e:
                    logger.error('Connect to IP Module failed (try %d/%d): %s' % (tries, max_tries, str(e)))
                except Exception:
                    logger.exception("Unable to connect to IP Module (try %d/%d)" % (tries, max_tries))

            tries += 1

        return False

    async def connect_to_site(self):
        loop = asyncio.get_event_loop()
        self.connection_timestamp = 0
        logger.info("Connecting to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        if self.site_info is None:
            self.site_info = self.get_site_info(siteid=cfg.IP_CONNECTION_SITEID, email=cfg.IP_CONNECTION_EMAIL)

        if self.site_info is None:
            logger.error("Unable to get site info")
            return False
        try:
            # xoraddr = binascii.unhexlify(self.site_info['site'][0]['module'][0]['xoraddr'])
            if self.site_info is None:
                logger.error("Unable to get site info")
                return False

            self.module = None

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
                self.module = self.site_info['site'][0]['module'][0]  # Use first

            if self.module is None:
                self.site_info = None  # Reset state
                logger.error("Unable to find module with desired panel serial")
                return False

            xoraddr = binascii.unhexlify(self.module['xoraddr'])

            stun_host = 'turn.paradoxmyhome.com'

            logger.debug("STUN TCP Change Request")
            self.stun_control = stun.StunClient(stun_host)
            self.stun_control.send_tcp_change_request()
            stun_r = self.stun_control.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            logger.debug("STUN TCP Binding Request")
            self.stun_control.send_binding_request()
            stun_r = self.stun_control.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            logger.debug("STUN Connect Request")
            self.stun_control.send_connect_request(xoraddr=xoraddr)
            stun_r = self.stun_control.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            self.connection_timestamp = time.time()

            connection_id = stun_r[0]['attr_body']
            raddr = self.stun_control.sock.getpeername()

            logger.debug("STUN Connection Bind Request")
            self.stun_tunnel = stun.StunClient(host=raddr[0], port=raddr[1])
            self.stun_tunnel.send_connection_bind_request(binascii.unhexlify(connection_id))
            stun_r = self.stun_tunnel.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            _, self.connection = await loop.create_connection(self.make_protocol, sock=self.stun_tunnel.sock)
            logger.info("Connected to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        except Exception:
            logger.exception("Unable to negotiate connection to site")
            return False

        return True

    async def connect_to_module(self):
        try:
            logger.info("Authenticating with IP Module")

            self.key = self.password  # first request is with initial password, next with generated by panel key

            self.connection.key = self.password
            payload = encrypt(self.password, self.key)

            msg = ip_message.build(
                dict(header=dict(length=len(self.key), unknown0=0x03, flags=0x09, command=0xf0, unknown1=0, encrypt=1),
                     payload=payload))
            self.connection.send_raw(msg)
            message_payload = await self.wait_for_message(raw=True)

            response = ip_payload_connect_response.parse(message_payload)

            if response.login_status != 'success':
                logger.error("Error connecting to IP Module. Wrong IP Module password?")
                return False

            logger.info("Authentication Success. IP Module version {:02x}, firmware: {}.{}, serial: {}".format(
                response.hardware_version,
                response.ip_firmware_major,
                response.ip_firmware_minor,
                binascii.hexlify(response.ip_module_serial).decode('utf-8')))

            self.key = response.key
            self.connection.key = response.key

            # F2
            logger.debug("Sending F2")
            msg = ip_message.build(
                dict(header=dict(length=0, unknown0=0x03, flags=0x09, command=0xf2, unknown1=0, encrypt=1),
                     payload=encrypt(b'', self.key)))
            self.connection.send_raw(msg)
            message_payload = await self.wait_for_message(raw=True)
            logger.debug("F2 answer: {}".format(binascii.hexlify(message_payload)))

            # # F4
            # logger.debug("Sending F4")
            # msg = binascii.unhexlify('aa00000309f400000001eeeeeeee0000')
            # self.connection.send_raw(msg)
            # message_payload = await self.wait_for_message(raw=True)
            #
            # logger.debug("F4 answer: {}".format(binascii.hexlify(message_payload)))

            # F3
            logger.debug("Sending F3")
            msg = ip_message.build(
                dict(header=dict(length=0, unknown0=0x03, flags=0x09, command=0xf3, unknown1=0, encrypt=1),
                     payload=encrypt(b'', self.key)))
            self.connection.send_raw(msg)
            message_payload = await self.wait_for_message(raw=True)

            #logger.debug("F3 answer: {}".format(binascii.hexlify(message_payload)))

            # F8
            logger.debug("Sending F8")
            payload = binascii.unhexlify('0a500080000000000000000000000000000000000000000000000000000000000000000000d0')
            payload_len = len(payload)
            payload = encrypt(payload, self.key)
            msg = ip_message.build(
                dict(header=dict(length=payload_len, unknown0=0x03, flags=0x09, command=0xf8, unknown1=0, encrypt=1),
                     payload=payload))
            self.connection.send_raw(msg)
            message_payload = await self.wait_for_message(raw=True)
            logger.debug("F8 answer: {}".format(binascii.hexlify(message_payload)))

            logger.info("Session Established with IP Module")

            self.connected = True
        except asyncio.TimeoutError:
            self.connected = False
            logger.error("Unable to establish session with IP Module. Timeout. Only one connection at a time is allowed.")
        except Exception as e:
            self.connected = False
            logger.exception("Unable to establish session with IP Module")

        return self.connected

    def write(self, data: bytes):
        """Write data to socket"""

        if not self.refresh_stun():
            raise ConnectionError('Failed to refresh STUN')

        return super(IPConnection, self).write(data)

    @staticmethod
    def get_site_info(email, siteid):
        logger.info("Getting site info")
        URL = "https://api.insightgoldatpmh.com/v1/site"

        headers = {'User-Agent': 'Mozilla/3.0 (compatible; Indy Library)', 'Accept-Encoding': 'identity',
                   'Accept': 'text/html, */*'}

        tries = 5
        while tries > 0:
            req = requests.get(URL, headers=headers, params={'email': email, 'name': siteid})
            if req.status_code == 200:
                return req.json()

            logger.warning("Unable to get site info. Retrying...")
            tries -= 1
            time.sleep(5)

        return None

    def refresh_stun(self):
        if self.site_info is None or self.connection_timestamp == 0:
            return True

        try:
            # Refresh session if required
            if time.time() - self.connection_timestamp >= 500:
                logger.info("Refreshing session")
                self.stun_control.send_refresh_request()
                stun_r = self.stun_control.receive_response()
                if stun.is_error(stun_r):
                    logger.error(stun.get_error(stun_r))
                    self.connected = False
                    return False

                self.connection_timestamp = time.time()

            return True
        except Exception:
            logger.exception("Session refresh")
            return False
