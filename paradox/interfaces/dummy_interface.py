# -*- coding: utf-8 -*-

import logging

from paradox.interfaces import Interface
from paradox.lib.utils import SortableTuple

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

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
        try:
            while True:
                item = self.queue.get()
                if item[1] == 'notify':
                    self.handle_notify(item[2])
                elif item[1] == 'command':
                    if item[2] == 'stop':
                        break
        except Exception:
            self.logger.exception("Dummy")

    def stop(self):
        """ Stops the Dummy interface"""
        self.queue.put_nowait(SortableTuple((2, 'command', 'stop')))

    def notify(self, source, message, level):
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

    def handle_notify(self, raw):
        sender, message, level = raw

        logger.log(level, "sender: %s, message: %s" % (sender, message))
