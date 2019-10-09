# -*- coding: utf-8 -*-

import logging
import re

from chump import Application

from paradox.config import config as cfg
from paradox.interfaces.text.core import AbstractTextInterface

logger = logging.getLogger('PAI').getChild(__name__)

class PushoverInterface(AbstractTextInterface):
    """Interface Class using Pushover"""
    name = 'pushover'

    def __init__(self):
        super().__init__(cfg.PUSHOVER_ALLOW_EVENTS, cfg.PUSHOVER_IGNORE_EVENTS)

        self.app = None
        self.users = {}

    def _run(self):
        logger.info("Starting Pushover Interface")

        self.app = Application(cfg.PUSHOVER_APPLICATION_KEY)
        if not self.app.is_authenticated:
            raise Exception('Failed to authenticate with Pushover. Please check PUSHOVER_APPLICATION_KEY')


    def _send_message(self, message):

        for user_key, devices_raw in cfg.PUSHOVER_BROADCAST_KEYS.items():
            user = self.users.get(user_key)

            if user is None:
                user = self.users[user_key] = self.app.get_user(user_key)

            if not user.is_authenticated:
                raise Exception(
                    'Failed to check user key with Pushover. Please check PUSHOVER_BROADCAST_KEYS[%s]' % user_key)

            if devices_raw == '*' or devices_raw is None:
                user.send_message(message, title='Alarm')
            else:
                devices = list(filter(bool, re.split('[\s]*,[\s]*', devices_raw)))

                for elem in (elem for elem in devices if elem not in user.devices):
                    logger.warning('%s is not in the Pushover device list for the user %s' % (elem, user_key))

                for device in devices:
                    user.send_message(message, title='PAI', device=device)

        # TODO: Missing the message reception