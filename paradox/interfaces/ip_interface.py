# -*- coding: utf-8 -*-

# IP Interface

import time
import logging
import socket
import select
from construct import GreedyBytes, Struct, Aligned, Const, Int8ub, Bytes, Int16ul, Default
from threading import Thread, Event
import binascii
import os
from typing import Awaitable
from paradox.lib.crypto import encrypt, decrypt
from paradox.lib.async_message_manager import RAWMessageHandler

import asyncio

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

ip_message = Struct(
    "header" / Aligned(16, Struct(
        "sof" / Const(0xaa, Int8ub),
        "length" / Int16ul,
        "unknown0" / Default(Int8ub, 0x01),
        "flags" / Int8ub,
        "command" / Int8ub,
        "sub_command" / Default(Int8ub, 0x00),
        'unknown1' / Default(Int8ub, 0x00),
        'encrypt' / Default(Int8ub, 0x03),
    ), b'\xee'),
    "payload" / Aligned(16, GreedyBytes, b'\xee'))

ip_payload_connect_response = Struct(
    'command' / Const(0x00, Int8ub),
    'key' / Bytes(16),
    'major' / Int8ub,
    'minor' / Int8ub,
    'ip_major' / Default(Int8ub, 5),
    'ip_minor' / Default(Int8ub, 2),
    'unknown' / Default(Int8ub, 0x00),
    'unknown2' / Default(Int8ub, 0x00),
    'unknown3' / Default(Int8ub, 0x00),
    'unknown4' / Default(Int8ub, 0xee)
)


class ClientConnection():
    def __init__(self, reader, writer, alarm, key):
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

            payload = encrypt(data, self.connection_key)
            flags = 0x73

            m = ip_message.build(
                dict(header=dict(length=payload_len, unknown0=2, flags=flags, command=0), payload=payload))

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("IPI -> APP (raw) {}".format(binascii.hexlify(m)))

            self.client_writer.write(m)

        return False  # Block further message processing

    async def handle(self):
        next_connection_key = self.connection_key
        status = 'connecting'

        while True:
            try:
                data = await self.client_reader.read(1000)
            except:
                logger.info("Client disconnected")
                break

            if not data:
                continue

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("APP -> IPI (raw) {}".format(binascii.hexlify(data)))

            message = ip_message.parse(data)
            in_payload = message.payload

            if len(in_payload) >= 16 and message.header.flags & 0x01 != 0 and len(in_payload) % 16 == 0:
                in_payload = decrypt(in_payload, self.connection_key)[:message.header.length]

            in_payload = in_payload[:message.header.length]

            assert len(in_payload) == message.header.length, "Message payload length does not match with length in " \
                                                             "header "
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("APP -> IPI (payload) {}".format(binascii.hexlify(in_payload)))

            force_plain_text = False
            response_code = 0x01
            out_payload = None
            if message.header.command == 0xf0:
                password = in_payload

                if password != self.interface_password:
                    logger.warn("Authentication Error")
                    break
                else:
                    logger.info("Authentication Success")

                # Generate a new key
                next_connection_key = binascii.hexlify(os.urandom(8)).upper()

                out_payload = ip_payload_connect_response.build(
                    dict(
                        key=next_connection_key,
                        major=0,
                        minor=32,
                        ip_major=1,
                        ip_minor=50,
                        unknown=113,
                        unknown2=6,
                        unknown3=0x15,
                        unknown4=44
                    ))

                flags = 0x39
            elif message.header.command == 0xf2:
                out_payload = b'\x00'
                flags = 0x39
            elif message.header.command == 0xf3:
                out_payload = binascii.unhexlify('0100000000000000000000000000000000')
                flags = 0x3b
            elif message.header.command == 0xf4:
                out_payload = b'\x01' if status == 'closing_connection' else b'\x00'
                flags = 0x39
            elif message.header.command == 0xf8:
                out_payload = b'\x01'
                flags = 0x39
            elif message.header.command == 0x00:
                response_code = 0x02
                flags = 0x73
                if in_payload[0] == 0x70 and in_payload[2] == 0x05:  # Close connection
                    out_payload = self.alarm.panel.get_message('CloseConnection').build({})
                    status = 'closing_connection'
                else:
                    try:
                        self.alarm.connection.write(in_payload)
                    except Exception:
                        logger.exception("Send to panel")
                        break

                if in_payload[0] == 0x00:  # Just a status update
                    status = 'connected'

            else:
                logger.warn("UNKNOWN: raw: {}, payload: {}".format(binascii.hexlify(data), binascii.hexlify(in_payload)))
                continue

            if out_payload is not None:
                payload_length = len(out_payload)

                if message.header.flags & 0x08 != 0:
                    out_payload = out_payload.ljust((payload_length // 16) * 16, bytes([0xee]))

                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("IPI -> IPI (payload) {}".format(binascii.hexlify(out_payload)))

                if message.header.flags & 0x01 != 0 and not force_plain_text:
                    out_payload = encrypt(out_payload, self.connection_key)

                m = ip_message.build(dict(
                    header=dict(
                        length=payload_length,
                        unknown0=response_code,
                        flags=flags,
                        command=message.header.command
                    ),
                    payload=out_payload))

                if cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("IPI -> APP (raw) {}".format(binascii.hexlify(m)))

                self.client_writer.write(m)
                await self.client_writer.drain()

                if self.connection_key != next_connection_key:
                    self.connection_key = next_connection_key

            if status == 'closing_connection':
                break

class IPInterface():
    def __init__(self):
        self.key = cfg.IP_INTERFACE_PASSWORD
        self.addr = cfg.IP_INTERFACE_BIND_ADDRESS
        self.port = cfg.IP_INTERFACE_BIND_PORT
        self.alarm = None
        self.server = None
        self.started = False
        self.name = 'ip_interface'
        self.client_nr = 0

    def set_alarm(self, alarm):
        logger.debug("Set alarm")
        self.alarm = alarm

        if not self.server and self.started:
            self.start()

    # def on_connection_lost(self):
    #     logger.error('Connection with client was lost')

    def stop(self):
        logger.info("Stopping IP Interface")
        if self.server is not None:
            self.server.cancel()
            self.server = None
        self.started = False

    def start(self):
        logger.info("Starting IP Interface")
        self.started = True
        if not self.alarm:
            logger.info("No alarm set")
            return

        coro = asyncio.start_server(self.handle_client, self.addr, self.port, loop=self.alarm.work_loop)
        self.server = self.alarm.work_loop.create_task(coro)

        logger.info("IP Interface started")

    def set_notify(self, tmp):
        pass

    def event(self, event):
        pass

    def notify(self, source, message, level):
        pass

    def change(self, element, label, panel_property, value):
        """ Enqueues a change """

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
        self.alarm.message_manager.register_handler(
            RAWMessageHandler(connection.handle_panel_message, name=handler_name)
        )

        logger.info("Client %d connected" % self.client_nr)
        await self.alarm.pause()

        await connection.handle()
        self.alarm.message_manager.deregister_handler(handler_name)

        logger.debug("Resuming")
        await self.alarm.resume()
        logger.info("Client %d disconnected" % self.client_nr)
