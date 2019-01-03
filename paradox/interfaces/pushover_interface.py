# -*- coding: utf-8 -*-

import logging
import re

from chump import Application

from config import user as cfg
from paradox.interfaces import Interface
from paradox.lib.utils import SortableTuple

logger = logging.getLogger('PAI').getChild(__name__)


class PushoverInterface(Interface):
    """Interface Class using Pushover"""
    name = 'pushover'

    def __init__(self):
        super().__init__()

        self.app = None
        self.users = {}

    def run(self):
        logger.info("Starting Pushover Interface")
        try:
            self.app = Application(cfg.PUSHOVER_APPLICATION_KEY)
            if not self.app.is_authenticated:
                raise Exception('Failed to authenticate with Pushover. Please check PUSHOVER_APPLICATION_KEY')

            while True:
                item = self.queue.get()
                if item[1] == 'notify':
                    self.handle_notify(item[2])
                elif item[1] == 'command':
                    if item[2] == 'stop':
                        break
        except Exception:
            logger.exception("Pushover")

    def stop(self):
        """ Stops the Pushover interface"""
        self.queue.put_nowait(SortableTuple((2, 'command', 'stop')))

    def notify(self, source, message, level):
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

    def handle_notify(self, raw):
        sender, message, level = raw
        if level < logging.INFO:
            return

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
                    user.send_message(message, title='Alarm', device=device)
