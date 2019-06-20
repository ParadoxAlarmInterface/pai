# -*- coding: utf-8 -*-

import logging
import re

from chump import Application

from pubsub import pub

from paradox.interfaces import Interface
from paradox.lib.utils import SortableTuple

from paradox.config import config as cfg

class PushoverInterface(Interface):
    """Interface Class using Pushover"""
    name = 'pushover'

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.app = None
        self.users = {}

    def run(self):
        self.logger.info("Starting Pushover Interface")
        try:
            self.app = Application(cfg.PUSHOVER_APPLICATION_KEY)
            if not self.app.is_authenticated:
                raise Exception('Failed to authenticate with Pushover. Please check PUSHOVER_APPLICATION_KEY')

            pub.subscribe(self.handle_panel_event, "pai_events")
            pub.subscribe(self.handle_notify, "pai_notifications")

            while True:
                item = self.queue.get()
                if item[1] == 'command':
                    if item[2] == 'stop':
                        break
        except Exception:
            self.logger.exception("Pushover")

    def stop(self):
        """ Stops the Pushover interface"""
        self.queue.put_nowait(SortableTuple((2, 'command', 'stop')))

    def notify(self, source, message, level):
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

    def handle_notify(self, message):
        sender, message, level = message
        if level < logging.INFO:
            return

        self.send_message(message)

    def handle_panel_event(self, event):
        """Handle Live Event"""

        if event.level < logging.INFO:
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
            self.send_message(event.message)

    def send_message(self, message):

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
                    self.logger.warning('%s is not in the Pushover device list for the user %s' % (elem, user_key))

                for device in devices:
                    user.send_message(message, title='Alarm', device=device)
