# -*- coding: utf-8 -*-

import json
import logging
import re
import time

from pushbullet import Pushbullet
from ws4py.client import WebSocketBaseClient
from ws4py.manager import WebSocketManager

from paradox.config import config as cfg
from paradox.event import EventLevel
# Pushbullet interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)


class PushBulletWSClient(WebSocketBaseClient):

    def init(self, interface):
        """ Initializes the PB WS Client"""

        self.pb = Pushbullet(cfg.PUSHBULLET_KEY, cfg.PUSHBULLET_SECRET)
        self.manager = WebSocketManager()
        self.alarm = None
        self.interface = interface

    def stop(self):
        self.terminate()
        self.manager.stop()

    def set_alarm(self, alarm):
        """ Sets the paradox alarm object """
        self.alarm = alarm

    def handshake_ok(self):
        """ Callback trigger when connection succeeded"""
        logger.info("Handshake OK")
        self.manager.add(self)
        self.manager.start()
        for chat in self.pb.chats:
            logger.debug("Associated contacts: {}".format(chat))

        # Receiving pending messages
        self.received_message(json.dumps({"type": "tickle", "subtype": "push"}))

        self.send_message("Active")

    def received_message(self, message):
        """ Handle Pushbullet message. It should be a command """
        logger.debug("Received Message {}".format(message))

        try:
            message = json.loads(str(message))
        except:
            logger.exception("Unable to parse message")
            return

        if self.alarm is None:
            return
        if message['type'] == 'tickle' and message['subtype'] == 'push':
            now = time.time()
            pushes = self.pb.get_pushes(modified_after=int(now) - 20, limit=1, filter_inactive=True)
            logger.debug("got pushes {}".format(pushes))
            for p in pushes:
                self.pb.dismiss_push(p.get("iden"))
                self.pb.delete_push(p.get("iden"))

                if p.get('direction') == 'outgoing' or p.get('dismissed'):
                    continue

                if p.get('sender_email_normalized') in cfg.PUSHBULLET_CONTACTS:
                    ret = self.interface.send_command(p.get('body'))

                    if ret:
                        logger.info("From {} ACCEPTED: {}".format(p.get('sender_email_normalized'), p.get('body')))
                    else:
                        logger.warning("From {} UNKNOWN: {}".format(p.get('sender_email_normalized'), p.get('body')))
                else:
                    logger.warning(
                        "Command from INVALID SENDER {}: {}".format(p.get('sender_email_normalized'), p.get('body')))

    def unhandled_error(self, error):
        logger.error("{}".format(error))

        try:
            self.terminate()
        except Exception:
            logger.exception("Closing Pushbullet WS")

        self.close()

    def send_message(self, msg, dstchat=None):
        if dstchat is None:
            dstchat = self.pb.chats

        if not isinstance(dstchat, list):
            dstchat = [dstchat]

        for chat in dstchat:
            if chat.email in cfg.PUSHBULLET_CONTACTS:
                try:
                    self.pb.push_note("paradox", msg, chat=chat)
                except Exception:
                    logger.exception("Sending message")
                    time.sleep(5)

    def notify(self, source, message, level):
        try:
            if level.value >= EventLevel.WARN.value:
                self.send_message("{}".format(message))
        except Exception:
            logging.exception("Pushbullet notify")


class PushBulletInterface(ThreadQueueInterface):
    """Interface Class using Pushbullet"""
    name = 'pushbullet'

    def __init__(self):
        super().__init__()

        self.pb = None
        self.pb_ws = None

    def run(self):
        logger.info("Starting Pushbullet Interface")
        try:
            self.pb_ws = PushBulletWSClient('wss://stream.pushbullet.com/websocket/{}'.format(cfg.PUSHBULLET_KEY))
            self.pb_ws.init(self)
            self.pb_ws.connect()

            ps.subscribe(self._handle_panel_event, "events")
            ps.subscribe(self._handle_notify, "notifications")

            super().run()
        except Exception:
            logger.exception("PB")

    def set_alarm(self, alarm):
        super().set_alarm(alarm)
        self.pb_ws.set_alarm(alarm)

    def stop(self):
        """ Stops the Pushbullet interface"""
        super().stop()
        self.pb_ws.stop()

    def _handle_panel_event(self, event):
        """Handle Live Event"""

        if event.level.value < EventLevel.INFO.value:
            return

        major_code = event.major
        minor_code = event.minor

        # Only let some elements pass
        allow = False
        for ev in cfg.PUSHBULLET_ALLOW_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = True
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = True
                    break

        # Ignore some events
        for ev in cfg.PUSHBULLET_IGNORE_EVENTS:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = False
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = False
                    break

        if allow:
            self.pb_ws.notify('panel', event.message, event.level)

    def _handle_notify(self, message):
        sender, message, level = message
        if sender == 'pushbullet':
            return

        if level < EventLevel.INFO.value:
            return

        self.pb_ws.notify(sender, message, level)
