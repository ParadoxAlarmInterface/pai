from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

from construct import Container

from paradox.connections.connection import Connection
from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.protocol import IPConnectionProtocol
from paradox.connections.ip.stun_session import StunSession
from paradox.connections.serial.protocol import SerialConnectionProtocol
from paradox.exceptions import PAICriticalException
from paradox.lib.handlers import FutureHandler, HandlerRegistry

logger = logging.getLogger("PAI").getChild(__name__)


#: Pause between connection attempts. The IP module accepts a single session
#: at a time and only frees the slot once it notices the old socket is gone,
#: so retrying immediately is a reliable way to be refused three times.
CONNECT_RETRY_DELAY = 5.0


class MultiAttemptConnection(Connection):
    async def connect(self) -> bool:
        tries = 1
        max_tries = 3
        self.connected = False

        while tries <= max_tries:
            logger.info("Connecting. Try %d/%d" % (tries, max_tries))
            succeeded = False
            try:
                try:
                    await self._try_connect()
                    succeeded = True
                    return True
                finally:
                    if not succeeded:
                        await self._discard_failed_attempt()
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
            if tries <= max_tries:
                await asyncio.sleep(CONNECT_RETRY_DELAY)

        return False

    async def _discard_failed_attempt(self) -> None:
        """Tear down a half-open attempt before retrying.

        ``_try_connect`` stores the protocol as soon as the socket opens and
        only then runs the module handshake, so a handshake failure leaves an
        open socket owned by nothing. Overwriting ``_protocol`` on the next try
        would strand it -- ``ConnectionProtocol`` deliberately does not close
        the transport on ``__del__`` -- leaving PAI to compete with its own
        orphans for the module's single session slot.
        """
        try:
            await self.close()
        except Exception:
            logger.debug(
                "Ignoring error while discarding a failed connection attempt",
                exc_info=True,
            )

    @abstractmethod
    async def _try_connect(self):
        raise NotImplementedError("Implement in a subclass")


class BareIPConnection(MultiAttemptConnection):
    def __init__(self, host="127.0.0.1", port=10000):
        super().__init__()
        self.host = host
        self.port = port

    async def _try_connect(self):
        _, self._protocol = await asyncio.get_running_loop().create_connection(
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
        return asyncio.get_running_loop().create_task(
            self.ip_handler_registry.handle(container)
        )

    async def wait_for_ip_message(self, timeout=None) -> Container:
        # ``None`` defers to cfg.IO_TIMEOUT inside wait_until_complete, which
        # reads it at call time rather than at import time.
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
        _, self._protocol = await asyncio.get_running_loop().create_connection(
            self._make_protocol, host=self.host, port=self.port
        )

        await IPModuleConnectCommand(self).execute()

        self.connected = True


class StunIPConnection(IPConnectionWithEncryption):
    def __init__(self, site_id, email, panel_serial, password):
        super().__init__(password)

        self.stun_session = StunSession(site_id, email, panel_serial)
        self._refresh_task: Optional[asyncio.Task] = None

    def on_connection_loss(self):
        super().on_connection_loss()

        if self.stun_session is not None:
            self.stun_session.close()

    async def close(self):
        # The tunnel socket is the transport's, but the control socket is
        # ours. A connect attempt that opens the STUN session and then fails
        # would otherwise leak it, and the TURN allocation with it.
        try:
            await super().close()
        finally:
            if self.stun_session is not None:
                self.stun_session.close()

    def write(self, data: bytes):
        """Write data to socket"""

        self._schedule_session_refresh()

        return super().write(data)

    def _schedule_session_refresh(self) -> None:
        """Renew the TURN allocation in the background, if it is due.

        The refresh used to run inline here, doing blocking socket I/O on the
        event loop: every ~500 s PAI stopped servicing the panel, MQTT and
        every other interface until the TURN server answered. The allocation
        still has ~100 s of life left when a refresh becomes due, so letting
        this write proceed while the renewal runs in a thread is both safe and
        what keeps a slow TURN server from looking like a panel dropout.
        """
        if self.stun_session is None or not self.stun_session.refresh_required():
            return

        if self._refresh_task is not None and not self._refresh_task.done():
            return  # One already in flight; do not queue a second.

        self._refresh_task = asyncio.get_running_loop().create_task(
            self._refresh_session()
        )

    async def _refresh_session(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.stun_session.refresh_session)
        except Exception:
            # The allocation is gone or the control socket is dead. Drop the
            # link so the main loop reconnects, rather than writing into a
            # tunnel that has already stopped forwarding.
            logger.error(
                "STUN session refresh failed, dropping connection", exc_info=True
            )
            await self.close()

    async def _try_connect(self) -> None:
        await self.stun_session.connect()
        _, self._protocol = await asyncio.get_running_loop().create_connection(
            self._make_protocol, sock=self.stun_session.get_socket()
        )

        await IPModuleConnectCommand(self).execute()

        self.connected = True
