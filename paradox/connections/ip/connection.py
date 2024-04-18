from abc import ABC, abstractmethod
import asyncio
import logging

from construct import Container

from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.stun_session import StunSession
from paradox.connections.protocols import IPConnectionProtocol, SerialConnectionProtocol
from paradox.exceptions import PAICriticalException
from paradox.lib.handlers import FutureHandler, HandlerRegistry

logger = logging.getLogger("PAI").getChild(__name__)


class MultiAttemptConnection(Connection):
    async def connect(self) -> bool:
        tries = 1
        max_tries = 3
        self.connected = False

        while tries <= max_tries:
            logger.info("Connecting. Try %d/%d" % (tries, max_tries))
            try:
                await self._try_connect()
                return True
            except asyncio.TimeoutError as e:
                logger.error(
                    "Timeout while establishing connection (try %d/%d): %s"
                    % (tries, max_tries, str(e))
                )
            except OSError as e:
                logger.error(
                    "Connect failed (try %d/%d): %s" % (tries, max_tries, str(e))
                )
            except PAICriticalException:
                raise
            except Exception as e:
                logger.exception(
                    "Unhandled exception while connecting (try %d/%d): %s"
                    % (tries, max_tries, str(e))
                )

            tries += 1

        return False

    @abstractmethod
    async def _try_connect(self):
        raise NotImplementedError("Implement in a subclass")


class BareIPConnection(MultiAttemptConnection):
    def __init__(self, host="127.0.0.1", port=10000):
        super().__init__()
        self.host = host
        self.port = port

    async def _try_connect(self):
        _, self._protocol = await self.loop.create_connection(
            self._make_protocol, host=self.host, port=self.port
        )

        self.connected = True

    def _make_protocol(self):
        return SerialConnectionProtocol(self)


class IPConnectionWithEncryption(MultiAttemptConnection, IPConnectionHandler, ABC):
    _protocol: IPConnectionProtocol

    def __init__(self, password=None):
        super().__init__()
        if isinstance(password, str):
            password = password.encode()
        self.password = password
        self.key = password

        self.ip_handler_registry = HandlerRegistry()

    def reset_key(self):
        self.set_key(self.password)

    def set_key(self, value):
        self.key = value
        self._protocol.key = value

    def on_ip_message(self, container: Container):
        return self.loop.create_task(self.ip_handler_registry.handle(container))

    async def wait_for_ip_message(self, timeout=cfg.IO_TIMEOUT) -> Container:
        future = FutureHandler()
        return await self.ip_handler_registry.wait_until_complete(future, timeout)

    async def send_raw_ip_message(self, msg):
        self._protocol.send_raw(msg)

    def _make_protocol(self):
        return IPConnectionProtocol(self, self.key)


class LocalIPConnection(IPConnectionWithEncryption):
    def __init__(
        self,
        host,
        port,
        password,
    ):
        super().__init__(password)
        self.host = host
        self.port = port

    async def _try_connect(self) -> None:
        _, self._protocol = await self.loop.create_connection(
            self._make_protocol, host=self.host, port=self.port
        )

        await IPModuleConnectCommand(self).execute()

        self.connected = True


class StunIPConnection(IPConnectionWithEncryption):
    def __init__(self, site_id, email, panel_serial, password):
        super().__init__(password)

        self.stun_session = StunSession(site_id, email, panel_serial)

    def on_connection_loss(self):
        super().on_connection_loss()

        if self.stun_session is not None:
            self.stun_session.close()

    def write(self, data: bytes):
        """Write data to socket"""

        if self.stun_session is not None:
            self.stun_session.refresh_session_if_required()

        return super().write(data)

    async def _try_connect(self) -> None:
        await self.stun_session.connect()
        _, self._protocol = await self.loop.create_connection(
            self._make_protocol, sock=self.stun_session.get_socket()
        )

        await IPModuleConnectCommand(self).execute()

        self.connected = True
