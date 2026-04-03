from abc import abstractmethod
import asyncio
import binascii
import logging

from paradox.config import config as cfg
from paradox.connections.handler import ConnectionHandler, IPConnectionHandler
from paradox.connections.ip.parsers import (
    IPMessageCommand,
    IPMessageRequest,
    IPMessageResponse,
    IPMessageType,
)
from paradox.connections.serial_encryption import (
    EncryptedSerialTransport,
    make_serial_key,
)
from paradox.lib.crypto import decrypt_serial_message

logger = logging.getLogger("PAI").getChild(__name__)


def checksum(data, min_message_length):
    """Calculates the 8bit checksum of Paradox messages"""
    c = 0

    if data is None or len(data) < min_message_length:
        return False

    for i in data[:-1]:
        c += i

    r = (c % 256) == data[-1]
    return r


class ConnectionProtocol(asyncio.Protocol):
    def __init__(self, handler: ConnectionHandler):
        self.transport = None
        self.use_variable_message_length = True
        self.buffer = b""

        self.handler = handler

        self._closed: asyncio.Future = None  # type: ignore[assignment]
        self.buffer = b""

    def connection_made(self, transport):
        self._closed = asyncio.get_running_loop().create_future()
        self.transport = transport

        self.handler.on_connection()

    def is_active(self) -> bool:
        return (
            bool(self.transport)
            and self._closed is not None
            and not self._closed.done()
        )

    def check_active(self):
        if not self.is_active():
            raise ConnectionError("Transport does not exist or is already closed")

    async def close(self):
        if self.transport:
            try:
                self.transport.close()
            except Exception:
                logger.exception("Connection transport close raised Exception")
            self.transport = None

        if self._closed is not None:
            await asyncio.wait_for(self._closed, timeout=cfg.IO_TIMEOUT)

    @abstractmethod
    def send_message(self, message):
        raise NotImplementedError("This function needs to be overridden in a subclass")

    def connection_lost(self, exc):
        logger.error(f"Connection was closed: {exc}")
        self.buffer = b""
        self.transport = None

        if self._closed is not None and not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)

        super().connection_lost(exc)

        # asyncio.get_event_loop().call_soon(self.on_con_lost)
        self.handler.on_connection_loss()

        self.handler = None

    def variable_message_length(self, mode):
        self.use_variable_message_length = mode

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed is not None and closed.done() and not closed.cancelled():
            closed.exception()


class SerialConnectionProtocol(ConnectionProtocol):
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
        self.buffer += recv_data

        min_length = 4 if self.use_variable_message_length else 37

        while len(self.buffer) >= min_length:
            is_encrypted_frame = False
            if self.use_variable_message_length:
                if self.buffer[0] >> 4 == 0:
                    potential_packet_length = 37
                elif self.buffer[0] >> 4 in [1, 3, 4, 5, 6, 7, 8, 9]:
                    potential_packet_length = (
                        self.buffer[1] if 0 < self.buffer[1] <= 71 else 37
                    )
                elif self.buffer[0] >> 4 in [0xA, 0xB, 0xD]:
                    potential_packet_length = self.buffer[1]
                elif self.buffer[0] >> 4 == 0xC:
                    potential_packet_length = self.buffer[1] * 256 + self.buffer[2]
                elif self.buffer[0] >> 4 == 0xE:
                    if self.buffer[1] == 0xFE:
                        if cfg.SERIAL_ENCRYPTED:
                            # Full-AES E0 FE: frame is [E0|x][FE][n*16 AES bytes][checksum].
                            # Scan AES block boundaries for the first valid checksum to
                            # determine frame length without a timeout.
                            found = False
                            for n_blocks in range(1, 8):
                                frame_len = 2 + n_blocks * 16 + 1
                                if len(self.buffer) < frame_len:
                                    break
                                candidate = self.buffer[:frame_len]
                                if sum(candidate[:-1]) % 256 == candidate[-1]:
                                    potential_packet_length = frame_len
                                    is_encrypted_frame = True
                                    found = True
                                    break
                            if not found:
                                break  # Wait for more data
                        else:
                            # BabyWare compact E0 FE: length byte at [2]
                            if len(self.buffer) < 3:
                                break
                            potential_packet_length = self.buffer[2]
                            is_encrypted_frame = True
                    elif self.buffer[1] < 37 or self.buffer[1] == 0xFF:
                        # MG/SP in 21st century and EVO Live Events. Probable values=0x13, 0x13, 0x00, 0xFF
                        potential_packet_length = 37
                    else:
                        potential_packet_length = self.buffer[1]
                else:
                    potential_packet_length = 37

            else:
                potential_packet_length = 37

            if len(self.buffer) < potential_packet_length:
                break

            frame = self.buffer[:potential_packet_length]

            if is_encrypted_frame or checksum(frame, min_length):
                self.buffer = self.buffer[len(frame) :]  # Remove message
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug(f"SER -> PAI {binascii.hexlify(frame)}")

                if cfg.SERIAL_ENCRYPTED and is_encrypted_frame:
                    decrypted = decrypt_serial_message(frame, self._serial_key)
                    if decrypted:
                        logger.debug(
                            f"SER DECRYPT: {len(frame)}b E0FE → {len(decrypted)}b"
                        )
                        self.handler.on_message(decrypted)
                    else:
                        logger.warning(
                            f"SER: E0FE AES decrypt failed: {binascii.hexlify(frame)}"
                        )
                else:
                    self.handler.on_message(frame)
            else:
                self.buffer = self.buffer[1:]


class IPConnectionProtocol(ConnectionProtocol):
    def __init__(self, handler: IPConnectionHandler, key):
        super().__init__(handler)

        self.handler = handler
        self.key = key

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
        self.buffer += recv_data

        if self.buffer[0] != 0xAA:
            if len(self.buffer) > 0:
                logger.warning(
                    "Dangling data in the receive buffer: %s"
                    % binascii.hexlify(self.buffer)
                )
            self.buffer = b""
            return

        if len(recv_data) + 16 < self.buffer[1]:
            return

        if len(self.buffer) % 16 != 0:
            return

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(f"IP -> PAI (raw) {binascii.hexlify(self.buffer)}")

        self._process_message(self.buffer)
        self.buffer = b""
