# -*- coding: utf-8 -*-

# IP Interface

import asyncio
import logging

from paradox.config import config as cfg
from paradox.interfaces import Interface

from ...lib.handlers import PersistentHandler
from .client_connection import ClientConnection

logger = logging.getLogger("PAI").getChild(__name__)


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

        self.client_nr = (self.client_nr + 1) % 256
        logger.info("Client %d connected" % self.client_nr)

        connection = ClientConnection(reader, writer, self.alarm, self.key)
        handler_name = "%s_%d" % (self.name, self.client_nr)
        self.alarm.connection.register_raw_handler(
            PersistentHandler(connection.handle_panel_raw_message, name=handler_name)
        )

        await self.alarm.pause()

        try:
            await connection.handle()
        except:
            logger.exception("Client %d connection raised exception" % self.client_nr)
        finally:
            self.alarm.connection.deregister_raw_handler(handler_name)

            asyncio.get_event_loop().create_task(self.alarm.resume())
            logger.info("Client %d disconnected" % self.client_nr)
