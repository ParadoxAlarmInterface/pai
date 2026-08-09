import binascii
import logging

from paradox.config import config as cfg
from paradox.connections.protocol_base import ConnectionProtocol
from paradox.connections.serial.encryption import (
    EncryptedSerialTransport,
    make_serial_key,
)
from paradox.connections.serial.framing import SerialFramer
from paradox.lib.crypto import decrypt_serial_message

logger = logging.getLogger("PAI").getChild(__name__)


class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(self, handler):
        super().__init__(handler)
        self._framer = SerialFramer()
        self._serial_key = None

    def connection_made(self, transport):
        if cfg.SERIAL_ENCRYPTED and cfg.PASSWORD:
            self._serial_key = make_serial_key(cfg.PASSWORD)
            transport = EncryptedSerialTransport(transport, self._serial_key)
            logger.info("Serial encryption enabled (SERIAL_ENCRYPTED=True)")
        else:
            self._serial_key = None
        super().connection_made(transport)

    def send_message(self, message):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"PAI -> SER {binascii.hexlify(message)}")

        self.check_active()
        self.transport.write(message)

    def data_received(self, recv_data):
        for frame in self._framer.feed(recv_data):
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug(f"SER -> PAI {binascii.hexlify(frame.data)}")

            if frame.encrypted and cfg.SERIAL_ENCRYPTED:
                self._deliver_encrypted(frame.data)
            else:
                self.handler.on_message(frame.data)

    def _deliver_encrypted(self, data: bytes) -> None:
        decrypted = decrypt_serial_message(data, self._serial_key)
        if decrypted:
            logger.debug(f"SER DECRYPT: {len(data)}b E0FE → {len(decrypted)}b")
            self.handler.on_message(decrypted)
        else:
            logger.warning(f"SER: E0FE AES decrypt failed: {binascii.hexlify(data)}")

    def reset_framing(self) -> None:
        self._framer.reset()

    def variable_message_length(self, mode: bool) -> None:
        self._framer.use_variable_message_length = mode

    @property
    def use_variable_message_length(self) -> bool:
        return self._framer.use_variable_message_length

    @property
    def buffer(self) -> bytes:
        """Unconsumed bytes. Retained for tests and diagnostics."""
        return self._framer.buffer.pending
