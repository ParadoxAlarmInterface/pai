# -*- coding: utf-8 -*-

# Pushbullet interface.
# Only exposes critical status changes and accepts commands
from paradox.interfaces import Interface

from ws4py.client import WebSocketBaseClient
from ws4py.manager import WebSocketManager

from pushbullet import Pushbullet

import time
import logging
import json

from paradox.event import EventLevel
from paradox.lib.utils import SortableTuple

from paradox.config import config as cfg


class PushBulletWSClient(WebSocketBaseClient):

    def init(self, interface):
        """ Initializes the PB WS Client"""

        self.logger = logging.getLogger('PAI').getChild(__name__)
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
        self.logger.info("Handshake OK")
        self.manager.add(self)
        self.manager.start()
        for chat in self.pb.chats:
            self.logger.debug("Associated contacts: {}".format(chat))

        # Receiving pending messages
        self.received_message(json.dumps({"type": "tickle", "subtype": "push"}))

        self.send_message("Active")

    def received_message(self, message):
        """ Handle Pushbullet message. It should be a command """
        self.logger.debug("Received Message {}".format(message))

        try:
            message = json.loads(str(message))
        except:
            self.logger.exception("Unable to parse message")
            return

        if self.alarm is None:
            return
        if message['type'] == 'tickle' and message['subtype'] == 'push':
            now = time.time()
            pushes = self.pb.get_pushes(modified_after=int(now) - 20, limit=1, filter_inactive=True)
            self.logger.debug("got pushes {}".format(pushes))
            for p in pushes:
                self.pb.dismiss_push(p.get("iden"))
                self.pb.delete_push(p.get("iden"))

                if p.get('direction') == 'outgoing' or p.get('dismissed'):
                    continue

                if p.get('sender_email_normalized') in cfg.PUSHBULLET_CONTACTS:
                    ret = self.interface.send_command(p.get('body'))

                    if ret:
                        self.logger.info("From {} ACCEPTED: {}".format(p.get('sender_email_normalized'), p.get('body')))
                    else:
                        self.logger.warning("From {} UNKNOWN: {}".format(p.get('sender_email_normalized'), p.get('body')))
                else:
                    self.logger.warning("Command from INVALID SENDER {}: {}".format(p.get('sender_email_normalized'), p.get('body')))

    def unhandled_error(self, error):
        self.logger.error("{}".format(error))

        try:
            self.terminate()
        except Exception:
            self.logger.exception("Closing Pushbullet WS")

        self.close()

    def send_message(self, msg, dstchat=None):
        for chat in self.pb.chats:
            if chat.email in cfg.PUSHBULLET_CONTACTS:
                try:
                    self.pb.push_note("paradox", msg, chat=chat)
                except Exception:
                    self.logger.exception("Sending message")
                    time.sleep(5)

    def notify(self, source, message, level):
        try:
            if level.value >= EventLevel.WARN.value:
                self.send_message("{}".format(message))
        except Exception:
            logging.exception("Pushbullet notify")


class PushBulletInterface(Interface):
    """Interface Class using Pushbullet"""
    name = 'pushbullet'

    def __init__(self):
        super().__init__()

        self.pb = None
        self.pb_ws = None

    def run(self):
        self.logger.info("Starting Pushbullet Interface")
        try:
            self.pb_ws = PushBulletWSClient('wss://stream.pushbullet.com/websocket/{}'.format(cfg.PUSHBULLET_KEY))
            self.pb_ws.init(self)
            self.pb_ws.connect()

            while True:
                item = self.queue.get()

                if item[1] == 'change':
                    self.handle_change(item[2])
                elif item[1] == 'event':
                    self.handle_event(item[2])
                elif item[1] == 'notify':
                    self.handle_notify(item[2])
                elif item[1] == 'command':
                    if item[2] == 'stop':
                        break
        except Exception:
            self.logger.exception("PB")

    def set_alarm(self, alarm):
        self.pb_ws.set_alarm(alarm)

    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        self.queue.put_nowait(SortableTuple((2, 'event', raw)))

    def change(self, element, label, property, value):
        """ Enqueues a change """
        self.queue.put_nowait(SortableTuple((2, 'change', (element, label, property, value))))

    def notify(self, source, message, level):
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

    def stop(self):
        """ Stops the Pushbullet interface"""
        self.queue.put_nowait(SortableTuple((2, 'command', 'stop')))
        self.pb_ws.stop()

    def handle_event(self, raw):
        self.pb_ws.notify('panel', raw.message, raw.level)

    def handle_change(self, raw):
        element, label, property, value = raw
        self.pb_ws.change(element, label, property, value)

    def handle_notify(self, raw):
        sender, message, level = raw
        if sender == 'pushbullet':
            return

        self.pb_ws.notify(sender, message, level)

