# -*- coding: utf-8 -*-

import asyncio
import binascii
import json
import logging
import time
import typing

import requests

from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.connections.ip.parsers import (IPMessageCommand, IPMessageRequest,
                                            IPPayloadConnectResponse)
from paradox.connections.protocols import (IPConnectionProtocol,
                                           SerialConnectionProtocol)
from paradox.exceptions import PAICriticalException
from paradox.lib import stun

logger = logging.getLogger("PAI").getChild(__name__)


class IPConnection(Connection):
    def __init__(
        self,
        on_message: typing.Callable[[bytes], None],
        host="127.0.0.1",
        port=10000,
        password=None,
    ):
        super(IPConnection, self).__init__(on_message=on_message)
        if isinstance(password, str):
            password = password.encode()
        self.password = password
        self.key = password
        self.host = host
        self.port = port
        self.site_info = None
        self.module = None
        self.connection_timestamp = 0

        self.stun_control = None
        self.stun_tunnel = None

    def on_connection_lost(self):
        logger.error("Connection to panel was lost")

        if self.stun_control:
            try:
                self.stun_control.close()
                self.stun_control = None
            except:
                logger.exception("stun_control socket close failed")
        if self.stun_tunnel:
            try:
                self.stun_tunnel.close()
                self.stun_tunnel = None
            except:
                logger.exception("stun_control socket close failed")

    async def close(self):
        self.connection_timestamp = 0

        await super(IPConnection, self).close()

    def make_protocol(self):
        if cfg.IP_CONNECTION_BARE:
            return SerialConnectionProtocol(
                self.on_message, self.on_bare_connection_open, self.on_connection_lost
            )
        else:
            return IPConnectionProtocol(
                self.on_message, self.on_connection_lost, self.key
            )

    def on_bare_connection_open(self):
        logger.info("Serial port open")
        self.connected = True

    async def connect(self) -> bool:
        tries = 1
        max_tries = 3

        while tries <= max_tries:

            if (
                cfg.IP_CONNECTION_SITEID is not None
                and cfg.IP_CONNECTION_EMAIL is not None
            ):
                try:
                    r = await self.connect_to_site()

                    if r and self.site_info is not None:
                        if await self.connect_to_module():
                            return True
                except:
                    logger.exception(
                        "Try %d/%d. Unable to connect to SITE ID" % (tries, max_tries)
                    )
            else:
                try:
                    logger.info(
                        "Connecting to IP module. Try %d/%d" % (tries, max_tries)
                    )

                    _, self._protocol = await self.loop.create_connection(
                        self.make_protocol, host=self.host, port=self.port
                    )
                    if cfg.IP_CONNECTION_BARE:
                        return True

                    if await self.connect_to_module():
                        return True
                except OSError as e:
                    logger.error(
                        "Connect to IP Module failed (try %d/%d): %s"
                        % (tries, max_tries, str(e))
                    )
                except PAICriticalException:
                    raise
                except:
                    logger.exception(
                        "Unable to connect to IP Module (try %d/%d)"
                        % (tries, max_tries)
                    )

            tries += 1

        return False

    async def connect_to_site(self):
        self.connection_timestamp = 0
        logger.info("Connecting to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        if self.site_info is None:
            self.site_info = await self.get_site_info(
                siteid=cfg.IP_CONNECTION_SITEID, email=cfg.IP_CONNECTION_EMAIL
            )

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
                for site in self.site_info["site"]:
                    for module in site:
                        logger.debug(
                            "Found module with panel serial: {}".format(
                                module["panelSerial"]
                            )
                        )
                        if module["panelSerial"] == cfg.IP_CONNECTION_PANEL_SERIAL:
                            self.module = module
                            break

                    if self.module is not None:
                        break
            else:
                self.module = self.site_info["site"][0]["module"][0]  # Use first

            if self.module is None:
                self.site_info = None  # Reset state
                logger.error("Unable to find module with desired panel serial")
                return False

            xoraddr = binascii.unhexlify(self.module["xoraddr"])

            stun_host = "turn.paradoxmyhome.com"

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

            connection_id = stun_r[0]["attr_body"]
            raddr = self.stun_control.sock.getpeername()

            logger.debug("STUN Connection Bind Request")
            self.stun_tunnel = stun.StunClient(host=raddr[0], port=raddr[1])
            self.stun_tunnel.send_connection_bind_request(
                binascii.unhexlify(connection_id)
            )
            stun_r = self.stun_tunnel.receive_response()
            if stun.is_error(stun_r):
                logger.error(stun.get_error(stun_r))
                return False

            _, self._protocol = await self.loop.create_connection(
                self.make_protocol, sock=self.stun_tunnel.sock
            )
            logger.info("Connected to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        except:
            logger.exception("Unable to negotiate connection to site")
            return False

        return True

    async def connect_to_module(self):
        try:
            logger.info("Authenticating with IP Module")

            self.key = (
                self.password
            )  # first request is with initial password, next with generated by panel key

            self._protocol.key = self.password

            msg = IPMessageRequest.build(
                dict(
                    header=dict(
                        command=IPMessageCommand.connect,
                        # sub_command=3,
                        sequence_id=1,
                    ),
                    payload=self.password,
                ),
                password=self.password,
            )
            self._protocol.send_raw(msg)
            message_payload = await self.wait_for_raw_message()

            response = IPPayloadConnectResponse.parse(message_payload)

            if response.login_status != "success":
                logger.error(f"Error connecting to IP Module: {response.login_status}")

                if response.login_status == "invalid_password":
                    raise PAICriticalException("Invalid IP Module password")
                return False

            logger.info(
                "Authentication Success. IP({}) Module version {:02x}, firmware: {}.{}, serial: {}".format(
                    response.ip_type,
                    response.hardware_version,
                    response.ip_firmware_major,
                    response.ip_firmware_minor,
                    binascii.hexlify(response.ip_module_serial).decode("utf-8"),
                )
            )

            self.key = response.key
            self._protocol.key = response.key

            # F2
            logger.debug("Sending keep alive request")
            msg = IPMessageRequest.build(
                dict(header=dict(command=IPMessageCommand.keep_alive)),
                password=self.key,
            )
            self._protocol.send_raw(msg)
            message_payload = await self.wait_for_raw_message()
            logger.debug(
                "Keep alive response: {}".format(binascii.hexlify(message_payload))
            )

            # # F4
            # logger.debug("Sending F4")
            # msg = binascii.unhexlify('aa00000309f400000001eeeeeeee0000')
            # self.connection.send_raw(msg)
            # message_payload = await self.wait_for_message(raw=True)
            #
            # logger.debug("F4 answer: {}".format(binascii.hexlify(message_payload)))

            # F3
            logger.debug("Sending upload download connection request")
            msg = IPMessageRequest.build(
                dict(header=dict(command=IPMessageCommand.upload_download_connection,)),
                password=self.key,
                cryptor_code=1
            )
            self._protocol.send_raw(msg)
            message_payload = await self.wait_for_raw_message()

            logger.debug("Upload download connection response: {}".format(binascii.hexlify(message_payload)))

            # F8
            logger.debug("Sending toggle keep alive request")
            payload = binascii.unhexlify(
                "0a500080000000000000000000000000000000000000000000000000000000000000000000d0"
            )
            msg = IPMessageRequest.build(
                dict(
                    header=dict(command=IPMessageCommand.toggle_keep_alive,),
                    payload=payload,
                ),
                password=self.key,
            )
            self._protocol.send_raw(msg)
            message_payload = await self.wait_for_raw_message()
            logger.debug(
                "Toggle keep alive response: {}".format(binascii.hexlify(message_payload))
            )

            logger.info("Session Established with IP Module")

            self.connected = True
        except asyncio.TimeoutError:
            self.connected = False
            logger.error(
                "Unable to establish session with IP Module. Timeout. Only one connection at a time is allowed."
            )
        except PAICriticalException:
            raise
        except:
            self.connected = False
            logger.exception("Unable to establish session with IP Module")

        return self.connected

    def write(self, data: bytes):
        """Write data to socket"""

        if not self.refresh_stun():
            raise ConnectionError("Failed to refresh STUN")

        return super(IPConnection, self).write(data)

    @staticmethod
    async def get_site_info(email, siteid):
        logger.info("Getting site info")
        URL = "https://api.insightgoldatpmh.com/v1/site"

        headers = {
            "User-Agent": "Mozilla/3.0 (compatible; Indy Library)",
            "Accept-Encoding": "identity",
            "Accept": "text/html, */*",
        }

        tries = 5
        loop = asyncio.get_event_loop()
        while tries > 0:
            req = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    URL, headers=headers, params={"email": email, "name": siteid}
                ),
            )
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
        except:
            logger.exception("Session refresh")
            return False
