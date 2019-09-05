# -*- coding: utf-8 -*-

import logging

from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

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

    def _handle_panel_event(self, event):
        level = event.level
        logger.log(level.value, event)
        logger.log(level.value, "message: %s" % event.message)
