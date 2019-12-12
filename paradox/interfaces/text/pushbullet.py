# -*- coding: utf-8 -*-

import json
import logging
import time

from pushbullet import Pushbullet
from ws4py.client import WebSocketBaseClient
from ws4py.manager import WebSocketManager

from paradox.config import config as cfg
from paradox.event import EventLevel, Notification
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps

# Pushbullet interface.
# Only exposes critical status changes and accepts commands

logger = logging.getLogger('PAI').getChild(__name__)


class PushBulletWSClient(WebSocketBaseClient):
    name = "pushbullet"

    def __init__(self, interface, url):
        """ Initializes the PB WS Client"""
        super().__init__(url)

        self.pb = Pushbullet(cfg.PUSHBULLET_KEY)
        self.manager = WebSocketManager()
        self.interface = interface
        
        self.device = None
        for i,device in enumerate(self.pb.devices):
            if device.nickname == 'pai':
                logger.debug("Device found")
                self.device = device
                break
        else:
            logger.exception("Device not found. Creating 'pai' device")
            self.device = self.pb.new_device(nickname='pai', icon='system')


    def stop(self):
        self.terminate()
        self.manager.stop()

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
        
        if message['type'] == 'tickle' and message['subtype'] == 'push':
            now = time.time()
            pushes = self.pb.get_pushes(modified_after=int(now) - 20, limit=1, filter_inactive=True)
            for p in pushes:
                
                # Ignore messages send by us
                if p.get('direction') == 'self' and p.get('title') == 'pai':
                    #logger.debug('Ignoring message sent')
                    continue
                
                if p.get('direction') == 'outgoing' or p.get('dismissed'):
                    #logger.debug('Ignoring outgoing dismissed')
                    continue
                
                if p.get('sender_email_normalized') in cfg.PUSHBULLET_CONTACTS or p.get('direction') == 'self':
                    ret = self.interface.handle_command(p.get('body'))

                    m = "PB {}: {}".format(p.get('sender_email_normalized'), ret)
                    logger.info(m)
                else:
                    m = "PB {} (UNK): {}".format(p.get('sender_email_normalized'), p.get('body'))
                    logger.warning(m)
                
                self.send_message(m)
                ps.sendNotification(Notification(sender=self.name, message=m, level=EventLevel.INFO))

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
        # Push to self
        self.device.push_note("pai", msg)
        
        for chat in dstchat:
            if chat.email in cfg.PUSHBULLET_CONTACTS:
                try:
                    self.pb.push_note("pai", msg, chat=chat)
                except Exception:
                    logger.exception("Sending message")
                    time.sleep(5)


class PushbulletTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using Pushbullet"""

    def __init__(self):
        super().__init__(cfg.PUSHBULLET_EVENT_FILTERS, cfg.PUSHBULLET_ALLOW_EVENTS, cfg.PUSHBULLET_IGNORE_EVENTS,
                         cfg.PUSHBULLET_MIN_EVENT_LEVEL)
        self.name = PushBulletWSClient.name
        self.pb_ws = None

    def _run(self):
        logger.info("Starting Pushbullet Interface")
        try:
            self.pb_ws = PushBulletWSClient(self, 'wss://stream.pushbullet.com/websocket/{}'.format(cfg.PUSHBULLET_KEY))
            self.pb_ws.connect()
        except:
            logger.exception("Could not connect to Pushbullet service")

        logger.info("Pushbullet Interface Started")

    def stop(self):
        """ Stops the Pushbullet interface"""
        super().stop()
        if self.pb_ws is not None:
            self.pb_ws.stop()

    def send_message(self, message: str, level: EventLevel):
        if self.pb_ws is not None:
            self.pb_ws.send_message(message)
