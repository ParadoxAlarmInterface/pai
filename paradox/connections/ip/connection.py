# -*- coding: utf-8 -*-

import asyncio
import binascii
import json
import logging
import time

import requests
from construct import Container

from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.protocols import (IPConnectionProtocol,
                                           SerialConnectionProtocol)
from paradox.exceptions import (ConnectToSiteFailed, PAICriticalException,
                                StunSessionRefreshFailed)
from paradox.lib import stun
from paradox.lib.handlers import FutureHandler, HandlerRegistry

logger = logging.getLogger("PAI").getChild(__name__)


class IPConnection(Connection, IPConnectionHandler):
    def __init__(
        self, host="127.0.0.1", port=10000, password=None,
    ):
        super(IPConnection, self).__init__()
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

        self.ip_handler_registry = HandlerRegistry()

    def reset_key(self):
        self.set_key(self.password)

    def set_key(self, value):
        self.key = value
        self._protocol.key = value

    def on_ip_message(self, container: Container):
        return self.loop.create_task(self.ip_handler_registry.handle(container))

    def on_connection(self):
        if cfg.IP_CONNECTION_BARE:
            logger.info("Serial port open")
            self.connected = True
        else:
            logger.info("Socket connection established")

    def on_connection_loss(self):
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
                logger.exception("stun_tunnel socket close failed")

    async def wait_for_ip_message(self, timeout=2) -> Container:
        future = FutureHandler()
        return await self.ip_handler_registry.wait_until_complete(future, timeout)

    async def send_raw_ip_message(self, msg):
        self._protocol.send_raw(msg)

    def write(self, data: bytes):
        """Write data to socket"""

        self._refresh_stun_if_required()

        return super(IPConnection, self).write(data)

    async def close(self):
        self.connection_timestamp = 0

        await super(IPConnection, self).close()

    async def connect(self) -> bool:
        tries = 1
        max_tries = 3
        self.connected = False

        while tries <= max_tries:
            logger.info("Connecting to IP module. Try %d/%d" % (tries, max_tries))
            try:
                if (
                    cfg.IP_CONNECTION_SITEID is not None
                    and cfg.IP_CONNECTION_EMAIL is not None
                ):
                    await self._connect_to_site()
                    _, self._protocol = await self.loop.create_connection(
                        self._make_protocol, sock=self.stun_tunnel.sock
                    )
                    logger.info(
                        "Connected to Site: {}".format(cfg.IP_CONNECTION_SITEID)
                    )
                else:
                    _, self._protocol = await self.loop.create_connection(
                        self._make_protocol, host=self.host, port=self.port
                    )
                    if cfg.IP_CONNECTION_BARE:
                        return True

                await IPModuleConnectCommand(self).execute()
                self.connected = True

                return self.connected

            except asyncio.TimeoutError:
                logger.error(
                    "Unable to establish session with IP Module. Timeout. Only one connection at a time is allowed."
                )
            except OSError as e:
                logger.error(
                    "Connect to IP Module failed (try %d/%d): %s"
                    % (tries, max_tries, str(e))
                )
            except PAICriticalException:
                raise
            except:
                logger.exception(
                    "Unhandled exception while connecting to IP Module (try %d/%d)"
                    % (tries, max_tries)
                )

            tries += 1

        return False

    def _make_protocol(self):
        if cfg.IP_CONNECTION_BARE:
            return SerialConnectionProtocol(self)
        else:
            return IPConnectionProtocol(self, self.key)

    async def _connect_to_site(self) -> None:
        self.connection_timestamp = 0
        logger.info("Connecting to Site: {}".format(cfg.IP_CONNECTION_SITEID))
        if self.site_info is None:
            self.site_info = await self._get_site_info(
                siteid=cfg.IP_CONNECTION_SITEID, email=cfg.IP_CONNECTION_EMAIL
            )

        if self.site_info is None:
            raise ConnectToSiteFailed("Unable to get site info")

        # xoraddr = binascii.unhexlify(self.site_info['site'][0]['module'][0]['xoraddr'])
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
            raise ConnectToSiteFailed("Unable to find module with desired panel serial")

        xoraddr = binascii.unhexlify(self.module["xoraddr"])

        stun_host = "turn.paradoxmyhome.com"

        logger.debug("STUN TCP Change Request")
        self.stun_control = stun.StunClient(stun_host)
        self.stun_control.send_tcp_change_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Change Request error: {stun.get_error(stun_r)}"
            )

        logger.debug("STUN TCP Binding Request")
        self.stun_control.send_binding_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Binding Request error: {stun.get_error(stun_r)}"
            )

        logger.debug("STUN Connect Request")
        self.stun_control.send_connect_request(xoraddr=xoraddr)
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN Connect Request error: {stun.get_error(stun_r)}"
            )

        self.connection_timestamp = time.time()

        connection_id = stun_r[0]["attr_body"]
        raddr = self.stun_control.sock.getpeername()

        logger.debug("STUN Connection Bind Request")
        self.stun_tunnel = stun.StunClient(host=raddr[0], port=raddr[1])
        self.stun_tunnel.send_connection_bind_request(binascii.unhexlify(connection_id))
        stun_r = self.stun_tunnel.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN Connection Bind Request error: {stun.get_error(stun_r)}"
            )

    @staticmethod
    async def _get_site_info(email, siteid):
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

    def _refresh_stun_if_required(self) -> None:
        if self.site_info is None or self.connection_timestamp == 0:
            return

        # Refresh session if required
        if time.time() - self.connection_timestamp >= 500:
            logger.info("STUN Session Refresh")
            self.stun_control.send_refresh_request()
            stun_r = self.stun_control.receive_response()
            if stun.is_error(stun_r):
                self.connected = False
                raise StunSessionRefreshFailed(
                    f"STUN Session Refresh failed: {stun.get_error(stun_r)}"
                )

            self.connection_timestamp = time.time()
