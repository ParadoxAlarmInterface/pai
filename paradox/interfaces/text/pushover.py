# -*- coding: utf-8 -*-

import logging
import re

import chump

from paradox.config import config as cfg
from paradox.event import EventLevel
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface

logger = logging.getLogger('PAI').getChild(__name__)

_level_2_priority = {
    EventLevel.NOTSET: chump.LOWEST,
    EventLevel.DEBUG: chump.LOWEST,
    EventLevel.INFO: chump.LOW,
    EventLevel.WARN: chump.NORMAL,
    EventLevel.ERROR: chump.HIGH,
    EventLevel.CRITICAL: chump.EMERGENCY
}

class PushoverTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using Pushover"""
    name = 'pushover'

    def __init__(self):
        super().__init__(cfg.PUSHOVER_EVENT_FILTERS, cfg.PUSHOVER_ALLOW_EVENTS, cfg.PUSHOVER_IGNORE_EVENTS,
                         cfg.PUSHOVER_MIN_EVENT_LEVEL)

        self.app = None
        self.users = {}

    def _run(self):
        logger.info("Starting Pushover Interface")

        self.app = chump.Application(cfg.PUSHOVER_KEY)
        if not self.app.is_authenticated:
            raise Exception('Failed to authenticate with Pushover. Please check PUSHOVER_APPLICATION_KEY')

    def send_message(self, message: str, level: EventLevel):
        for user_key, devices_raw in cfg.PUSHOVER_BROADCAST_KEYS.items():
            user = self.users.get(user_key)  # type: chump.User

            if user is None:
                user = self.users[user_key] = self.app.get_user(user_key)

            if not user.is_authenticated:
                raise Exception(
                    'Failed to check user key with Pushover. Please check PUSHOVER_BROADCAST_KEYS[%s]' % user_key)

            if devices_raw == '*' or devices_raw is None:
                user.send_message(message, title='Alarm', priority=_level_2_priority.get(level, chump.NORMAL))
            else:
                devices = list(filter(bool, re.split('[\s]*,[\s]*', devices_raw)))

                for elem in (elem for elem in devices if elem not in user.devices):
                    logger.warning('%s is not in the Pushover device list for the user %s' % (elem, user_key))

                for device in devices:
                    user.send_message(message, title='PAI', device=device, priority=_level_2_priority.get(level, chump.NORMAL))

        # TODO: Missing the message reception
