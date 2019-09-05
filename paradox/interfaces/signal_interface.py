# -*- coding: utf-8 -*-

import logging
import re

from gi.repository import GLib
from pydbus import SystemBus

from paradox.config import config as cfg
from paradox.event import EventLevel
# Signal interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)


class SignalInterface(ThreadQueueInterface):
    """Interface Class using Signal"""
    name = 'signal'

    def __init__(self):
        super().__init__()

        self.signal = None

    def stop(self):
        """ Stops the Signal Interface Thread"""
        logger.debug("Stopping Signal Interface")
        if self.loop is not None:
            self.stop_running.set()
            self.loop.quit()

        logger.debug("Signal Stopped")

    def run(self):
        logger.info("Starting Signal Interface")

        bus = SystemBus()

        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self._handle_message
        self.loop = GLib.MainLoop()

        # self.timer = GObject.idle_add(self.run_loop)

        logger.debug("Signal Interface Running")

        ps.subscribe(self._handle_panel_event, "events")
        ps.subscribe(self._handle_notify, "notifications")

        try:
            self.loop.run()

        except (KeyboardInterrupt, SystemExit):
            logger.debug("Signal loop stopping")
            if self.alarm is not None:
                self.loop.quit()
                self.alarm.disconnect()
        except Exception:
            logger.exception("Signal loop")

    def _send_message(self, message):
        if self.signal is None:
            logger.warning("Signal not available when sending message")
            return
        try:
            self.signal.sendMessage(str(message), [], cfg.SIGNAL_CONTACTS)
        except Exception:
            logger.exception("Signal send message")

    def _handle_message(self, timestamp, source, groupID, message, attachments):
        """ Handle Signal message. It should be a command """

        logger.debug("Received Message {} {} {} {} {}".format(
            timestamp, message, groupID, message, attachments))

        if self.alarm is None:
            return

        if source in cfg.SIGNAL_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("ACCEPTED: {}".format(message))
                self._send_message("ACCEPTED: {}".format(message))
            else:
                logger.warning("REJECTED: {}".format(message))
                self._send_message("REJECTED: {}".format(message))
        else:
            logger.warning("REJECTED: {}".format(message))
            self._send_message("REJECTED: {}".format(message))

    def _handle_notify(self, message):
        sender, message, level = message
        if level < EventLevel.INFO.value:
            return

        self._send_message(message)

    def _handle_panel_event(self, event):
        """Handle Live Event"""

        if event.level.value < EventLevel.INFO.value:
            return

        major_code = event.major
        minor_code = event.minor

        # Only let some elements pass
        allow = False
        for ev in cfg.SIGNAL_ALLOW_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = True
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = True
                    break

        # Ignore some events
        for ev in cfg.SIGNAL_IGNORE_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = False
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = False
                    break

        if allow:
            self._send_message(event.message)
