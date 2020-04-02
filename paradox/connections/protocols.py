import asyncio
import binascii
import logging
import typing

from paradox.config import config as cfg
from paradox.connections.ip.parsers import (IPMessageCommand, IPMessageRequest,
                                            IPMessageResponse, IPMessageType)
from paradox.lib.crypto import decrypt, encrypt

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
    def __init__(self, on_message: typing.Callable[[bytes], None], on_con_lost):
        self.transport = None
        self.use_variable_message_length = True
        self.buffer = b""

        self.on_message = on_message
        self.on_con_lost = on_con_lost

        self._closed = asyncio.get_event_loop().create_future()
        self.buffer = b""

    def connection_made(self, transport):
        self.transport = transport

    def is_active(self) -> bool:
        return bool(self.transport) and not self._closed.done()

    def check_active(self):
        if not self.is_active():
            raise ConnectionError("Transport does not exist or is already closed")

    async def close(self):
        if self.transport:
            try:
                self.transport.close()
            except:
                logger.exception("Connection transport close raised Exception")
            self.transport = None

        await asyncio.wait_for(self._closed, timeout=1)

    def send_message(self, message):
        raise NotImplementedError("This function needs to be overridden in a subclass")

    def connection_lost(self, exc):
        logger.error(f"Connection was closed: {exc}")
        self.buffer = b""
        self.transport = None

        if not self._closed.done():
            if exc is None:
                self._closed.set_result(None)
            else:
                self._closed.set_exception(exc)

        super().connection_lost(exc)

        # asyncio.get_event_loop().call_soon(self.on_con_lost)
        self.on_con_lost()

        self.on_message = None
        self.on_con_lost = None

    def variable_message_length(self, mode):
        self.use_variable_message_length = mode

    def __del__(self):
        # Prevent reports about unhandled exceptions.
        # Better than self._closed._log_traceback = False hack
        closed = self._closed
        if closed.done() and not closed.cancelled():
            closed.exception()


class SerialConnectionProtocol(ConnectionProtocol):
    def __init__(
        self, on_message: typing.Callable[[bytes], None], on_port_open, on_con_lost
    ):
        super(SerialConnectionProtocol, self).__init__(
            on_message=on_message, on_con_lost=on_con_lost
        )
        self.on_port_open = on_port_open

    def connection_made(self, transport):
        super(SerialConnectionProtocol, self).connection_made(transport)
        self.on_port_open()

    def send_message(self, message):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> SER {}".format(binascii.hexlify(message)))

        self.check_active()

        self.transport.write(message)

    def data_received(self, recv_data):
        self.buffer += recv_data

        min_length = 4 if self.use_variable_message_length else 37

        while len(self.buffer) >= min_length:
            if self.use_variable_message_length:
                if self.buffer[0] >> 4 == 0:
                    potential_packet_length = 37
                elif self.buffer[0] >> 4 in [1, 3, 4, 5, 6, 7, 8, 9]:
                    potential_packet_length = (
                        self.buffer[1] if 0 < self.buffer[1] <= 71 else 37
                    )
                elif self.buffer[0] >> 4 in [0x0A, 0x0B, 0x0D]:
                    potential_packet_length = self.buffer[1]
                elif self.buffer[0] >> 4 == 0x0C:
                    potential_packet_length = self.buffer[1] * 256 + self.buffer[2]
                elif self.buffer[0] >> 4 == 0x0E:
                    if self.buffer[1] < 37 or self.buffer[1] == 0xFF:
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

            if checksum(frame, min_length):
                self.buffer = self.buffer[len(frame) :]  # Remove message
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("SER -> PAI {}".format(binascii.hexlify(frame)))

                self.on_message(frame)
            else:
                self.buffer = self.buffer[1:]


class IPConnectionProtocol(ConnectionProtocol):
    def __init__(self, on_message: typing.Callable[[bytes], None], on_con_lost, key):
        super(IPConnectionProtocol, self).__init__(
            on_message=on_message, on_con_lost=on_con_lost
        )
        self.key = key

    def send_raw(self, raw):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> Mod {}".format(binascii.hexlify(raw)))

        self.check_active()

        self.transport.write(raw)

    def send_message(self, message):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PAI -> IPC {}".format(binascii.hexlify(message)))

        self.check_active()

        payload = encrypt(message, self.key)
        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    length=len(message),
                    message_type=IPMessageType.serial_passthrough_request,
                    command=IPMessageCommand.panel_communication,
                ),
                payload=payload,
            )
        )
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("IPC -> Mod {}".format(binascii.hexlify(msg)))

        self.transport.write(msg)

    def _get_message_payload(self, data):
        message = IPMessageResponse.parse(data)

        if (
            len(message.payload) >= 16
            and len(message.payload) % 16 == 0
            and message.header.flags.encrypt
        ):
            message_payload = decrypt(data[16:], self.key)[: message.header.length]
        else:
            message_payload = message.payload[: message.header.length]

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("IPC -> PAI {}".format(binascii.hexlify(message_payload)))

        return message_payload

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
            logger.debug("Mod -> IPC {}".format(binascii.hexlify(self.buffer)))

        self.on_message(self._get_message_payload(self.buffer))
        self.buffer = b""
