# -*- coding: utf-8 -*-

import logging

from paradox.interfaces import Interface
from paradox.lib.utils import SortableTuple

logger = logging.getLogger('PAI').getChild(__name__)

from paradox.lib import ps

class DummyInterface(Interface):
    """Interface Class using Dummy"""
    name = 'dummy'

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.app = None
        self.users = {}

    def run(self):
        self.logger.info("Starting Dummy Interface")

        ps.subscribe(self.handle_panel_event, "events")
        ps.subscribe(self.handle_notify, "notifications")

        try:
            while True:
                item = self.queue.get()
                if item[1] == 'command':
                    if item[2] == 'stop':
                        break
        except Exception:
            self.logger.exception("Dummy")

    def stop(self):
        """ Stops the Dummy interface"""
        self.queue.put_nowait(SortableTuple((2, 'command', 'stop')))

    def handle_notify(self, message):
        sender, message, level = message
        logger.log(level, "sender: %s, message: %s" % (message))

    def handle_panel_event(self, event):
        level = event.level
        logger.log(level.value, event)
        logger.log(level.value, "message: %s" % (event.message))