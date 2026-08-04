"""asyncio glue for the IP150 link. Framing lives in :mod:`.framing`."""

import binascii
import logging

from paradox.config import config as cfg
from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.framing import IPFramer
from paradox.connections.ip.parsers import (
    IPMessageCommand,
    IPMessageRequest,
    IPMessageResponse,
    IPMessageType,
)
from paradox.connections.protocol_base import ConnectionProtocol

logger = logging.getLogger("PAI").getChild(__name__)


class IPConnectionProtocol(ConnectionProtocol):
    def __init__(self, handler: IPConnectionHandler, key):
        super().__init__(handler)

        self.key = key
        self._framer = IPFramer()

    def send_raw(self, raw):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"PAI -> IP (raw) {binascii.hexlify(raw)}")

        self.check_active()

        self.transport.write(raw)

    def send_message(self, message):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"PAI -> IP (payload) {binascii.hexlify(message)}")

        self.check_active()

        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    length=len(message),
                    message_type=IPMessageType.serial_passthrough_request,
                    flags=dict(installer_mode=True),
                    command=IPMessageCommand.passthrough,
                    wt=100,
                    cryptor_code="aes_256_ecb",
                ),
                payload=message,
            ),
            password=self.key,
        )
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"PAI -> IP (raw) {binascii.hexlify(msg)}")

        self.transport.write(msg)

    def _process_message(self, data):
        message = IPMessageResponse.parse(data, password=self.key)

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"IP -> PAI (payload) {binascii.hexlify(message.payload)}")

        if message.header.message_type == IPMessageType.serial_passthrough_response:
            self.handler.on_message(message.payload)
        elif message.header.message_type == IPMessageType.ip_response:
            self.handler.on_ip_message(message)
        else:
            logger.error(f"Wrong message detected: {message}")

    def data_received(self, recv_data):
        for frame in self._framer.feed(recv_data):
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug(f"IP -> PAI (raw) {binascii.hexlify(frame.data)}")
            self._process_message(frame.data)

    def reset_framing(self) -> None:
        self._framer.reset()

    @property
    def buffer(self) -> bytes:
        """Unconsumed bytes. Retained for tests and diagnostics."""
        return self._framer.buffer.pending
