# -*- coding: utf-8 -*-

# IP Interface

import asyncio
import binascii
import logging
import os
from typing import Awaitable

from construct import Container
from paradox.config import config as cfg
from paradox.connections.ip.parsers import (IPMessageCommand, IPMessageRequest,
                                            IPMessageResponse, IPMessageType,
                                            IPPayloadConnectResponse)
from paradox.interfaces import Interface
from paradox.lib.async_message_manager import RAWMessageHandler

logger = logging.getLogger("PAI").getChild(__name__)


class ClientConnection:
    def __init__(self, reader, writer, alarm, key):
        if isinstance(key, str):
            key = key.encode()
        self.client_writer = writer
        self.client_reader = reader
        self.alarm = alarm
        self.interface_password = key
        self.connection_key = key

    async def handle_panel_message(self, data):
        """
        Handle message from panel, which must be sent to the client
        """
        if isinstance(data, Awaitable):
            try:
                data = await data
            except asyncio.TimeoutError:
                return False

        if data is not None:
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PNL -> IPI (payload) {}".format(binascii.hexlify(data)))

            payload_len = len(data)

            m = IPMessageResponse.build(
                dict(
                    header=dict(
                        length=payload_len,
                        message_type=IPMessageType.serial_passthrough_response,
                        flags=dict(encrypt=True, other=39),
                        command=0,
                    ),
                    payload=data,
                ),
                password = self.connection_key
            )

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IPI -> APP (raw) {}".format(binascii.hexlify(m)))

            self.client_writer.write(m)

        return False  # Block further message processing

    async def handle(self):
        next_connection_key = self.connection_key
        status = "connecting"

        while True:
            try:
                data = await asyncio.wait_for(
                    self.client_reader.read(1000), cfg.KEEP_ALIVE_INTERVAL * 1.5
                )
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

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug(
                    "APP -> IPI (payload) {}".format(binascii.hexlify(in_message.payload))
                )

            out_message_container = Container(
                header=Container(
                    message_type=IPMessageType.ip_response,
                    command=in_message.header.command,
                    flags=Container(encrypt=in_message.header.flags.encrypt),
                ),
                payload=b"",
            )

            if in_message.header.command == IPMessageCommand.ip_authentication:
                logger.info("Authenticating to IP interface")
                password = in_message.payload

                if password != self.interface_password:
                    logger.warning("Authentication Error: Wrong password")
                    out_message_container.header.flags.encrypt = False
                    out_message_container.header.flags.other_flags = 0x18
                    out_message_container.payload = IPPayloadConnectResponse.build(
                        dict(
                            key=b"\00" * 16,
                            login_status="invalid_password",
                            hardware_version=0,
                            ip_firmware_major=0,
                            ip_firmware_minor=0,
                            ip_module_serial=b"\x00\x00\x00\x00",
                        )
                    )
                    status = "closing_connection"
                else:
                    logger.info("Authentication Success")

                    # Generate a new key
                    next_connection_key = binascii.hexlify(os.urandom(8)).upper()

                    out_message_container.header.flags.other_flags = 0x1C
                    out_message_container.payload = IPPayloadConnectResponse.build(
                        dict(
                            key=next_connection_key,
                            login_status="success",
                            hardware_version=32,
                            ip_firmware_major=1,
                            ip_firmware_minor=32,
                            ip_module_serial=b"\x01\x23\x45\x67",
                        )
                    )
            elif in_message.header.command == IPMessageCommand.F2:
                out_message_container.header.flags.other_flags = 0x1C
                out_message_container.payload = b"\x00"
            elif in_message.header.command == IPMessageCommand.F3:
                out_message_container.header.flags.other_flags = 0x1D  # 4 in Babyware
                out_message_container.payload = binascii.unhexlify(
                    "0100000000000000000000000000000000"
                )
            elif in_message.header.command == IPMessageCommand.F4:
                out_message_container.header.flags.other_flags = 0x1C
                out_message_container.payload = (
                    b"\x01" if status == "closing_connection" else b"\x00"
                )
            elif in_message.header.command == IPMessageCommand.F8:
                out_message_container.header.flags.other_flags = 0x1C  # 3D in Babyware
                out_message_container.payload = b"\x01"
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
            elif in_message.header.command == IPMessageCommand.panel_communication:
                out_message_container.header.message_type = (
                    IPMessageType.serial_passthrough_response
                )
                out_message_container.header.flags.other_flags = 0x39

                if in_message.payload[0] == 0x70 and in_message.payload[2] == 0x05:  # Close connection
                    out_message_container.payload = self.alarm.panel.get_message(
                        "CloseConnection"
                    ).build({})
                    status = "closing_connection"
                else:
                    try:
                        async with self.alarm.request_lock, self.alarm.busy:
                            self.alarm.connection.write(in_message.payload)
                    except:
                        logger.exception("Send to panel")
                        break

                if in_message.payload[0] == 0x00:  # Just a status update
                    status = "connected"

            else:
                logger.warning(
                    "UNKNOWN: raw: {}, payload: {}".format(
                        binascii.hexlify(data), binascii.hexlify(in_message.payload)
                    )
                )
                continue

            payload_length = len(out_message_container.payload)  # TODO: Why can't payload be empty?
            if payload_length:
                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug(
                        "IPI -> APP (payload) {}".format(
                            binascii.hexlify(out_message_container.payload)
                        )
                    )

                m = IPMessageResponse.build(out_message_container, password=self.connection_key)

                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("IPI -> APP (raw) {}".format(binascii.hexlify(m)))

                self.client_writer.write(m)
                await self.client_writer.drain()

                if self.connection_key != next_connection_key:
                    self.connection_key = next_connection_key

            if status == "closing_connection":
                break


class IPInterface(Interface):
    def __init__(self, alarm):
        super().__init__(alarm)
        self.key = cfg.IP_INTERFACE_PASSWORD
        self.addr = cfg.IP_INTERFACE_BIND_ADDRESS
        self.port = cfg.IP_INTERFACE_BIND_PORT
        self.server = None
        self.started = False
        self.client_nr = 0

    # def on_connection_lost(self):
    #     logger.error('Connection with client was lost')

    def stop(self):
        if self.server is not None:
            self.server.close()
            self.server = None
        self.started = False

    def start(self):
        logger.info("Starting %s Interface", self.name)
        self.started = True

        if not self.alarm:
            logger.info("No alarm set")
            return

        asyncio.get_event_loop().create_task(self.run())

    async def run(self):
        try:
            self.server = await asyncio.start_server(
                self.handle_client, self.addr, self.port, loop=self.alarm.work_loop
            )
            logger.info(
                "IP Interface: serving on {}".format(
                    self.server.sockets[0].getsockname()
                )
            )
            logger.info("IP Interface started")
        except Exception as e:
            logger.error("Failed to start IP Interface {}".format(e))

    async def handle_client(self, reader, writer):
        """
        Handle message from the remote client.

        :param reader: Socket read stream from the client
        :param writer: Socket write stream to the client
        :return: None
        """
        connection = ClientConnection(reader, writer, self.alarm, self.key)

        self.client_nr = (self.client_nr + 1) % 256
        handler_name = "%s_%d" % (self.name, self.client_nr)
        self.alarm.connection.register_handler(
            RAWMessageHandler(connection.handle_panel_message, name=handler_name)
        )

        logger.info("Client %d connected" % self.client_nr)
        await self.alarm.pause()

        try:
            await connection.handle()
        except:
            logger.exception("Client %d connection raised exception" % self.client_nr)
        finally:
            self.alarm.connection.deregister_handler(handler_name)

            asyncio.get_event_loop().create_task(self.alarm.resume())
            logger.info("Client %d disconnected" % self.client_nr)
