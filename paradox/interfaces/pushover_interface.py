# -*- coding: utf-8 -*-

import logging
import re

from chump import Application

from paradox.config import config as cfg
from paradox.event import EventLevel
from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)


class PushoverInterface(ThreadQueueInterface):
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

            ps.subscribe(self._handle_panel_event, "events")
            ps.subscribe(self._handle_notify, "notifications")

            super().run()
        except Exception:
            logger.exception("Pushover")

    def _handle_notify(self, message):
        if message['level'] < EventLevel.INFO:
            return

        if message['source'] != self.name:
            self.pb_ws.notify(message['source'], message['payload'], message['level'])

    def _handle_panel_event(self, event):
        """Handle Live Event"""

        if event.level < EventLevel.INFO:
            return

        major_code = event.major
        minor_code = event.minor

        # Only let some elements pass
        allow = False
        for ev in cfg.PUSHOVER_ALLOW_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = True
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = True
                    break

        # Ignore some events
        for ev in cfg.PUSHOVER_IGNORE_EVENTS:
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
                    user.send_message(message, title='Alarm', device=device)
