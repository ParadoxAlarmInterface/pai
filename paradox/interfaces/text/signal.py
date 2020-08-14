# -*- coding: utf-8 -*-
import asyncio
import logging

from gi.repository import GLib
from paradox.config import config as cfg
from paradox.event import EventLevel, Notification
# Signal interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps
from pydbus import SystemBus

logger = logging.getLogger("PAI").getChild(__name__)


class SignalTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using Signal"""

    def __init__(self, alarm):
        super().__init__(
            alarm,
            cfg.SIGNAL_EVENT_FILTERS,
            cfg.SIGNAL_ALLOW_EVENTS,
            cfg.SIGNAL_IGNORE_EVENTS,
            cfg.SIGNAL_MIN_EVENT_LEVEL,
        )

        self.signal = None
        self.loop = None

    def stop(self):

        """ Stops the Signal Interface Thread"""
        if self.loop is not None:
            self.loop.quit()

        super().stop()

        logger.debug("Signal Stopped")

    def _run(self):
        super(SignalTextInterface, self)._run()

        bus = SystemBus()

        self.signal = bus.get("org.asamk.Signal")
        self.signal.onMessageReceived = self.handle_message
        self.loop = GLib.MainLoop()

        logger.debug("Signal Interface Running")

        self.loop.run()

    def send_message(self, message: str, level: EventLevel):
        if self.signal is None:
            logger.warning("Signal not available when sending message")
            return

        try:
            self.signal.sendMessage(str(message), [], cfg.SIGNAL_CONTACTS)
        except:
            logger.exception("Signal send message")

    def handle_message(self, timestamp, source, groupID, message, attachments):
        """ Handle Signal message. It should be a command """

        logger.debug(
            "Received Message {} {} {} {} {}".format(
                timestamp, message, groupID, message, attachments
            )
        )

        if source in cfg.SIGNAL_CONTACTS:
            future = asyncio.run_coroutine_threadsafe(
                self.handle_command(message), self.alarm.work_loop
            )
            ret = future.result(10)

            m = "Signal {} : {}".format(source, ret)
            logger.info(m)
        else:
            m = "Signal {} (UNK): {}".format(source, message)
            logger.warning(m)

        self.send_message(m, EventLevel.INFO)
        ps.sendNotification(
            Notification(sender=self.name, message=m, level=EventLevel.INFO)
        )
