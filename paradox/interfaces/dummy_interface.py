# -*- coding: utf-8 -*-

import logging

from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps
from paradox.event import Event, LiveEvent, ChangeEvent

logger = logging.getLogger('PAI').getChild(__name__)


class DummyInterface(ThreadQueueInterface):
    """Interface Class using Dummy"""
    name = 'dummy'

    def run(self):
        logger.info("Starting Dummy Interface")

        ps.subscribe(self._handle_panel_event, "events")
        ps.subscribe(self._handle_notify, "notifications")

        super().run()

    def _handle_notify(self, message):
        sender, message, level = message
        logger.log(level, "sender: %s, message: %s" % (sender, message))

    def _handle_panel_event(self, event: Event):
        level = event.level
        # logger.log(level.value, event)
        if isinstance(event, LiveEvent):
            logger.log(level.value, "LiveEvent message: %s" % event.message)
        elif isinstance(event, ChangeEvent):
            logger.log(level.value, "ChangeEvent message: %s" % event.message)
        else:
            logger.log(level.value, "%s message: %s" % (event.__class__.__name__, event.message))