# -*- coding: utf-8 -*-

import logging

from paradox.interfaces.text.core import AbstractTextInterface
from paradox.lib.event_filter import EventTagFilter
from paradox.lib import ps
from paradox.event import Event, LiveEvent, ChangeEvent, EventLevel, Notification
from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class DummyInterface(AbstractTextInterface):
    """Interface Class using Dummy"""
    name = 'dummy'

    def __init__(self):
        min_level = EventLevel.from_name(cfg.DUMMY_MIN_EVENT_LEVEL)
        event_filter = EventTagFilter(queries=cfg.DUMMY_EVENT_FILTERS, min_level=min_level)
        super().__init__(event_filter=event_filter)

    def handle_notify(self, notification: Notification):
        if self.notification_filter(notification):
            logger.log(notification.level, "sender: %s, message: %s" % (notification.sender, notification.message))

    def handle_panel_event(self, event: Event):
        if self.event_filter.match(event):
            level = event.level
            # logger.log(level.value, event)
            if isinstance(event, LiveEvent):
                logger.log(level.value, "LiveEvent message: %s" % event.message)
            elif isinstance(event, ChangeEvent):
                logger.log(level.value, "ChangeEvent message: %s" % event.message)
            else:
                logger.log(level.value, "%s message: %s" % (event.__class__.__name__, event.message))