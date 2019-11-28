# -*- coding: utf-8 -*-

import logging

from gi.repository import GLib
from pydbus import SystemBus

from paradox.config import config as cfg
from paradox.event import EventLevel
# Signal interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces.text.core import AbstractTextInterface
from paradox.lib import ps
from paradox.lib.event_filter import LiveEventRegexpFilter

logger = logging.getLogger('PAI').getChild(__name__)


class SignalTextInterface(AbstractTextInterface):
    """Interface Class using Signal"""
    name = 'signal'

    def __init__(self):
        event_filter = LiveEventRegexpFilter(cfg.SIGNAL_ALLOW_EVENTS, cfg.SIGNAL_IGNORE_EVENTS)
        super().__init__(event_filter=event_filter)

        self.signal = None
        self.loop = None

    def stop(self):

        """ Stops the Signal Interface Thread"""
        logger.debug("Stopping Signal Interface")
        if self.loop is not None:
            self.loop.quit()

        super().stop()

        logger.debug("Signal Stopped")

    def _run(self):
        logger.info("Starting Signal Interface")

        bus = SystemBus()

        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self.handle_message
        self.loop = GLib.MainLoop()

        logger.debug("Signal Interface Running")

        self.loop.run()

    def send_message(self, message):
        if self.signal is None:
            logger.warning("Signal not available when sending message")
            return

        try:
            self.signal.sendMessage(str(message), [], cfg.SIGNAL_CONTACTS)
        except Exception:
            logger.exception("Signal send message")

    def handle_message(self, timestamp, source, groupID, message, attachments):
        """ Handle Signal message. It should be a command """

        logger.debug("Received Message {} {} {} {} {}".format(
            timestamp, message, groupID, message, attachments))

        if source in cfg.SIGNAL_CONTACTS:
            ret = self.handle_command(message)

            m = "Signal {} : {}".format(source, ret)
            logger.info(m)
        else:
            m = "Signal {} (UNK): {}".format(source, message)
            logger.warning(m)

        self.send_message(m)
        ps.sendMessage("notifications",
                       message=dict(source=self.name,
                                    payload=m,
                                    level=EventLevel.INFO))
