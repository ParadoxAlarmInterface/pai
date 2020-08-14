import asyncio
import binascii
import logging
import os
from enum import Enum, auto
from typing import Awaitable, Union

from construct import Container

from paradox.config import config as cfg
from paradox.connections.ip.parsers import (IPMessageCommand, IPMessageRequest,
                                            IPMessageResponse, IPMessageType,
                                            IPPayloadConnectResponse)

logger = logging.getLogger("PAI").getChild(__name__)


class Status(Enum):
    CONNECTING = (auto(),)
    CONNECTED = (auto(),)
    CLOSING_CONNECTION = auto()


class ClientConnection:
    def __init__(self, reader, writer, alarm, key):
        self.status = Status.CONNECTING
        if isinstance(key, str):
            key = key.encode()
        self.client_writer = writer
        self.client_reader = reader
        self.alarm = alarm
        self.interface_password = key
        self.connection_key = key
        self.flags = Container(encrypt=True)

    async def handle_panel_raw_message(self, raw: bytes):
        """
        Handle message from panel, which must be sent to the client
        """

        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.serial_passthrough_response,
                command=IPMessageCommand.passthrough,
                flags=Container(
                    keep_alive=True,
                    live_events=True,
                    neware=True,
                    upload_download=True,
                    encrypt=self.flags.encrypt,
                ),
                sb=3,
                wt=0,
            ),
            payload=raw,
        )

        await self._send_to_client(out_message_container)

    async def handle(self):
        while True:
            try:
                data = await self._client_read()
            except asyncio.TimeoutError:
                logger.info("Timeout. Client may have disconnected")
                break
            except:
                logger.info("Client disconnected")
                break

            if not data:
                if not self.alarm.connection.connected:
                    break
                continue

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("APP -> IPI (raw) {}".format(binascii.hexlify(data)))

            in_message = IPMessageRequest.parse(data, password=self.connection_key)

            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug("APP -> IPI (message) {}".format(in_message))

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug(
                    "APP -> IPI (payload) {}".format(
                        binascii.hexlify(in_message.payload)
                    )
                )

            if in_message.header.message_type == IPMessageType.ip_request:
                if in_message.header.command == IPMessageCommand.connect:
                    await self._handle_ip_authentication(in_message)
                elif in_message.header.command == IPMessageCommand.keep_alive:
                    await self._handle_keep_alive(in_message)
                elif (
                    in_message.header.command
                    == IPMessageCommand.upload_download_connection
                ):
                    await self._handle_upload_download_connection(in_message)
                elif (
                    in_message.header.command
                    == IPMessageCommand.upload_download_disconnection
                ):
                    await self._handle_upload_download_disconnection(in_message)
                elif in_message.header.command == IPMessageCommand.toggle_keep_alive:
                    await self._handle_toggle_keep_alive(in_message)

                # FB - Multicommand
                # F5 - no idea
                # elif message.header.command in ["F5", "FB"]:  # Proxy Insite Gold communication
                #     TODO: Implement
                #     if not isinstance(self.alarm.connection, IPConnection):
                #         logger.error(f"Only IP Connection supports '{message.header.command}' command")
                #         break
                #
                #     proxy_message = Container(
                #         header=message.header,
                #         payload=in_payload
                #     )
                #
                #     async with self.alarm.request_lock, self.alarm.busy:
                #         self.alarm.connection.write_with_header(IPMessageRequest(proxy_message))

                else:
                    logger.warning(
                        f"Unknown ip_request: raw: {binascii.hexlify(data)}, message: {in_message}"
                    )
                    continue
            elif (
                in_message.header.message_type
                == IPMessageType.serial_passthrough_request
            ):
                if in_message.header.command == IPMessageCommand.passthrough:
                    await self._handle_passthrough(in_message)

                else:
                    logger.warning(
                        f"Unknown serial_passthrough_request: raw: {binascii.hexlify(data)}, message: {in_message}"
                    )

            if self.status == Status.CLOSING_CONNECTION:
                break

    async def _handle_passthrough(self, in_message):
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.message_type = (
            IPMessageType.serial_passthrough_response
        )
        out_message_container.header.flags.upload_download = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.header.flags.keep_alive = True
        if (
            in_message.payload[0] == 0x70 and in_message.payload[2] == 0x05
        ):  # Close connection
            out_message_container.payload = self.alarm.panel.get_message(
                "CloseConnection"
            ).build({})
            self.status = Status.CLOSING_CONNECTION
        else:
            async with self.alarm.request_lock, self.alarm.busy:
                self.alarm.connection.write(in_message.payload)
        if in_message.payload[0] == 0x00:  # Just a status update
            self.status = Status.CONNECTED

    async def _handle_ip_authentication(self, in_message):
        logger.info("Authenticating to IP interface")
        password = in_message.payload
        if password != self.interface_password:
            await self._handle_failed_login(in_message)
        else:
            await self._handle_successful_login(in_message)

    async def _send_to_client(self, container):
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug(
                "IPI -> APP (payload) {}".format(binascii.hexlify(container.payload))
            )
        raw = IPMessageResponse.build(container, password=self.connection_key)
        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("IPI -> APP (raw) {}".format(binascii.hexlify(raw)))
        self.client_writer.write(raw)
        await self.client_writer.drain()

    async def _handle_toggle_keep_alive(self, in_message):
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.upload_download = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.header.flags.keep_alive = True
        out_message_container.payload = b"\x01"

        await self._send_to_client(out_message_container)

    async def _handle_upload_download_disconnection(self, in_message):
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.payload = (
            b"\x01" if self.status == Status.CLOSING_CONNECTION else b"\x00"
        )

        await self._send_to_client(out_message_container)

    async def _handle_upload_download_connection(self, in_message):
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.upload_download = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.payload = binascii.unhexlify(
            "0100000000000000000000000000000000"
        )

        await self._send_to_client(out_message_container)

    async def _handle_keep_alive(self, in_message):
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.payload = b"\x00"

        await self._send_to_client(out_message_container)

    async def _handle_successful_login(self, in_message):
        logger.info("Authentication Success")
        # Generate a new key
        next_connection_key = binascii.hexlify(os.urandom(8)).upper()

        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.neware = True
        out_message_container.header.flags.live_events = True
        out_message_container.payload = IPPayloadConnectResponse.build(
            dict(
                key=next_connection_key,
                login_status="success",
                hardware_version=32,
                ip_firmware_major=1,
                ip_firmware_minor=32,
                ip_module_serial=b"\x71\x23\x45\x67",  # 0x71 = IP150
            )
        )

        await self._send_to_client(out_message_container)

        self.connection_key = next_connection_key

    async def _handle_failed_login(self, in_message):
        logger.warning("Authentication Error: Wrong password")
        out_message_container = Container(
            header=Container(
                message_type=IPMessageType.ip_response,
                command=in_message.header.command,
                flags=Container(encrypt=in_message.header.flags.encrypt),
                sb=3,
                wt=0,
            )
        )
        out_message_container.header.flags.encrypt = False
        out_message_container.header.flags.installer_mode = True
        out_message_container.header.flags.neware = True
        out_message_container.payload = IPPayloadConnectResponse.build(
            dict(
                key=b"\00" * 16,
                login_status="invalid_password",
                hardware_version=0,
                ip_firmware_major=0,
                ip_firmware_minor=0,
                ip_module_serial=b"\x71\x00\x00\x00",
            )
        )
        self.status = Status.CLOSING_CONNECTION

        await self._send_to_client(out_message_container)

    async def _client_read(self) -> bytes:
        return await asyncio.wait_for(
            self.client_reader.read(1000), cfg.KEEP_ALIVE_INTERVAL * 1.5
        )
