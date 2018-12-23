# -*- coding: utf-8 -*-

# Signal interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import Interface

from pydbus import SystemBus

from gi.repository import GLib
from gi.repository import GObject

import logging
import queue

from paradox.lib.utils import SortableTuple
from config import user as cfg


logger = logging.getLogger('PAI').getChild(__name__)


class SignalInterface(Interface):
    """Interface Class using Signal"""
    name = 'signal'

    def __init__(self):
        super().__init__()

        self.queue = queue.PriorityQueue()
        self.partitions = dict()
        self.signal = None
        self.logger = logger

    def stop(self):
        """ Stops the Signal Interface Thread"""
        logger.debug("Stopping Signal Interface")
        if self.loop is not None:
            self.stop_running.set()
            self.loop.quit()

        logger.debug("Signal Stopped")

    def notify(self, source, message, level):
        if source == self.name:
            return

        if level < logging.INFO:
            return

        self.queue.put_nowait(SortableTuple(
            (2, 'notify', (source, message, level))))

    def run(self):
        logger.info("Starting Signal Interface")

        bus = SystemBus()

        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self.handle_message
        self.loop = GLib.MainLoop()

        self.timer = GObject.idle_add(self.run_loop)

        logger.debug("Signal Interface Running")
        try:
            self.loop.run()

        except (KeyboardInterrupt, SystemExit):
            logger.debug("Signal loop stopping")
            if self.alarm is not None:
                self.loop.quit()
                self.alarm.disconnect()
        except Exception:
            logger.exception("Signal loop")

    def run_loop(self):
        try:
            item = self.queue.get(block=True, timeout=1)

            if item[1] == 'change':
                self.handle_change(item[2])
            elif item[1] == 'event':
                self.handle_event(item[2])
            elif item[1] == 'notify':
                self.send_message("{}: {}".format(item[2][0], item[2][1]))

        except queue.Empty as e:
            return True
        except Exception:
            logger.exception("loop")

        return True

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

        if self.alarm is None:
            return

        if source in cfg.SIGNAL_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("ACCEPTED: {}".format(message))
                self.send_message("ACCEPTED: {}".format(message))
            else:
                logger.warning("REJECTED: {}".format(message))
                self.send_message("REJECTED: {}".format(message))
        else:
            logger.warning("REJECTED: {}".format(message))
            self.send_message("REJECTED: {}".format(message))

    def handle_event(self, raw):
        """Handle Live Event"""

        major_code = raw['major'][0]
        minor_code = raw['minor'][1]

        # Ignore some events
        for ev in cfg.SIGNAL_IGNORE_EVENTS:
            if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                return

        return super(SignalInterface, self).handle_event(raw)
