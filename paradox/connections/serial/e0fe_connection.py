"""Session handling for a panel link in ``E0 FE`` mode.

On top of the wire format (:mod:`.e0fe_protocol`), the mode changes three
things in the session ``Paradox`` runs:

* after the plain identify exchange, the identify reply is echoed back
  wrapped, with byte 35 set to ``0xBA``. The panel answers with a wrapped
  copy of the identify whose byte 35 is ``0x00``; only then does
  StartCommunication follow, with ``source_id`` 0;
* a request without a reply ends the session and is reported as a
  ``ConnectionError``: it is never retransmitted, as the shared seq/seed
  state is unknown after it;
* CloseConnection is acknowledged with ``72 04 05 7b``, which is awaited
  briefly before the transport is closed. It is only sent while no other
  request is outstanding.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from construct import Container

from paradox.config import config
from paradox.connections.connection import Connection, Exchange
from paradox.connections.framing import checksum
from paradox.connections.serial.e0fe_framing import IDENTIFY_HEADER, IDENTIFY_LENGTH
from paradox.connections.serial.e0fe_protocol import E0FESerialConnectionProtocol
from paradox.exceptions import PAICriticalException
from paradox.lib.handlers import FutureHandler

logger = logging.getLogger("PAI").getChild(__name__)

cfg: Any = config

#: Byte 35 of the identify reply: what the panel sends when it expects the
#: wrapped handshake, what the echo carries, and what the panel's answer holds.
IDENTIFY_MODE_OFFSET = 35
IDENTIFY_MODE_PANEL = 0xA0
IDENTIFY_MODE_ECHO = 0xBA
IDENTIFY_MODE_ANSWER = 0x00

#: The panel and firmware this mode has been tested with: family and product
#: id (identify bytes 6-7) and application version (bytes 9-11).
TESTED_PRODUCT = bytes.fromhex("a15a")
TESTED_FIRMWARE = bytes.fromhex("078601")

CLOSE = bytes.fromhex("70040579")
CLOSE_ACK = bytes.fromhex("7204057b")

#: Seconds to wait for :data:`CLOSE_ACK` on disconnect.
CLOSE_ACK_TIMEOUT = 2.0


def _raw(message: Container) -> Optional[bytes]:
    try:
        data = message.fields.data + message.checksum
    except (AttributeError, KeyError, TypeError):
        return None
    return data if isinstance(data, bytes) else None


def _identify_echo(identify: bytes) -> bytes:
    echo = identify[:IDENTIFY_MODE_OFFSET] + bytes([IDENTIFY_MODE_ECHO])
    return echo + bytes([sum(echo) & 0xFF])


def _is_identify_answer(identify: bytes) -> Callable[[Container], bool]:
    def check(message: Container) -> bool:
        raw = _raw(message)
        return (
            raw is not None
            and len(raw) == IDENTIFY_LENGTH
            and raw[:IDENTIFY_MODE_OFFSET] == identify[:IDENTIFY_MODE_OFFSET]
            and raw[IDENTIFY_MODE_OFFSET] == IDENTIFY_MODE_ANSWER
        )

    return check


class E0FEConnection(Connection):
    """Mixin for connections whose protocol is
    :class:`~.e0fe_protocol.E0FESerialConnectionProtocol`.

    List it before the concrete connection class, which keeps its transport
    handling and only has to build the E0 FE protocol.
    """

    start_communication_source_id = 0x0
    retransmit_requests = False

    async def close_ended_session(self) -> None:
        """Let a session the protocol ended (see ``invalidate``) finish closing.

        Call before connecting again, so the old session's connection loss
        cannot be reported against the new one.
        """
        try:
            await self.close()  # type: ignore[no-untyped-call]
        except asyncio.TimeoutError:
            logger.warning("E0 FE: previous session did not close in time")
        except Exception as e:
            # A transport lost with an error reports it again on close.
            logger.debug("E0 FE: previous session ended with %r", e)

    def _e0fe_protocol(self) -> Optional[E0FESerialConnectionProtocol]:
        protocol = self._protocol
        return protocol if isinstance(protocol, E0FESerialConnectionProtocol) else None

    async def on_initiate_communication(
        self, reply: Container, exchange: Exchange
    ) -> None:
        identify = _raw(reply)
        if (
            identify is None
            or len(identify) != IDENTIFY_LENGTH
            or identify[:2] != IDENTIFY_HEADER
            or not checksum(identify)
        ):
            raise ConnectionError("E0 FE: invalid identify reply")
        if identify[IDENTIFY_MODE_OFFSET] != IDENTIFY_MODE_PANEL:
            raise PAICriticalException(
                "E0 FE: identify byte %d is 0x%02x, expected 0x%02x; is the panel "
                "in E0 FE serial mode?"
                % (
                    IDENTIFY_MODE_OFFSET,
                    identify[IDENTIFY_MODE_OFFSET],
                    IDENTIFY_MODE_PANEL,
                )
            )
        if identify[6:8] != TESTED_PRODUCT or identify[9:12] != TESTED_FIRMWARE:
            logger.warning(
                "E0 FE: only tested with an EVO192 on firmware 7.86.001; this "
                "panel reports product %s, firmware %x.%02x.%03x",
                identify[6:8].hex(),
                identify[9],
                identify[10],
                identify[11],
            )

        protocol = self._e0fe_protocol()
        if protocol is None:
            raise ConnectionError("E0 FE: not connected")
        protocol.start_wrapping()

        logger.info("E0 FE: switching to the E0 FE wrapping")
        answer = await exchange(_identify_echo(identify), _is_identify_answer(identify))
        if answer is None:
            raise ConnectionError("E0 FE: panel did not answer the identify echo")

    async def wait_for_message(
        self,
        check_fn: Optional[Callable[[Container], bool]] = None,
        timeout: float = cfg.IO_TIMEOUT,
    ) -> Container:
        protocol = self._e0fe_protocol()
        try:
            return await super().wait_for_message(check_fn, timeout)
        except asyncio.TimeoutError as e:
            reason = "no reply within %.1f s" % timeout
            if protocol is not None:
                protocol.invalidate(reason)
            raise ConnectionError("E0 FE: %s" % reason) from e

    async def end_session(self) -> None:
        protocol = self._e0fe_protocol()
        if protocol is None or not protocol.awaiting_reply_to(CLOSE):
            return

        try:
            await self.raw_handler_registry.wait_until_complete(
                FutureHandler(lambda raw: raw == CLOSE_ACK), CLOSE_ACK_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("E0 FE: panel did not acknowledge CloseConnection")
        else:
            logger.info("E0 FE: panel acknowledged CloseConnection")
