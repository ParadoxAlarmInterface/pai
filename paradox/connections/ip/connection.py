# -*- coding: utf-8 -*-

import asyncio
import logging

from construct import Container

from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.stun_session import StunSession
from paradox.connections.protocols import (IPConnectionProtocol,
                                           SerialConnectionProtocol)
from paradox.exceptions import PAICriticalException
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

        self.ip_handler_registry = HandlerRegistry()

        self.stun_session: StunSession = None

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

        if self.stun_session is not None:
            self.stun_session.close()

    async def wait_for_ip_message(self, timeout=2) -> Container:
        future = FutureHandler()
        return await self.ip_handler_registry.wait_until_complete(future, timeout)

    async def send_raw_ip_message(self, msg):
        self._protocol.send_raw(msg)

    def write(self, data: bytes):
        """Write data to socket"""

        if self.stun_session is not None:
            self.stun_session.refresh_session_if_required()

        return super(IPConnection, self).write(data)

    async def connect(self) -> bool:
        tries = 1
        max_tries = 3
        self.connected = False

        while tries <= max_tries:
            logger.info("Connecting to IP module. Try %d/%d" % (tries, max_tries))
            try:
                await self._try_connect()
                self.connected = True
                return True
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

    async def _try_connect(self) -> None:
        if cfg.IP_CONNECTION_SITEID is not None and cfg.IP_CONNECTION_EMAIL is not None:
            self.stun_session = StunSession()
            await self.stun_session.connect()
            _, self._protocol = await self.loop.create_connection(
                self._make_protocol, sock=self.stun_session.get_socket()
            )
        else:
            _, self._protocol = await self.loop.create_connection(
                self._make_protocol, host=self.host, port=self.port
            )
            if cfg.IP_CONNECTION_BARE:
                return

        await IPModuleConnectCommand(self).execute()

    def _make_protocol(self):
        if cfg.IP_CONNECTION_BARE:
            return SerialConnectionProtocol(self)
        else:
            return IPConnectionProtocol(self, self.key)
