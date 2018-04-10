# Pushbullet interface.
# Only exposes critical status changes and accepts commands

from ws4py.client import WebSocketBaseClient
from ws4py.manager import WebSocketManager
from ws4py import format_addresses, configure_logger

from pushbullet import Pushbullet

import time
import logging
import datetime
import json

from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)

class PushBulletWSClient(WebSocketBaseClient):

    def init(self):
        """ Initializes the PB WS Client"""

        self.pb = Pushbullet(PUSHBULLET_KEY, PUSHBULLET_SECRET)
        self.manager = WebSocketManager()
        self.alarm = None

    def set_alarm(self, alarm):
        """ Sets the paradox alarm object """
        self.alarm = alarm

    def handshake_ok(self):
        """ Callback trigger when connection succeeded"""
        logger.info("Handshake OK")
        self.manager.add(self)
        for chat in self.pb.chats:
            logger.debug("Associated contacts: {}".format(chat))

        # Receiving pending messages
        self.received_message(json.dumps({"type": "tickle", "subtype": "push"}))
       

    def handle_message(self, message):
        """ Handle Pushbullet message. It should be a command """

        logger.debug("Received Message {}".format(message))
        try:
            message = json.loads(str(message))
        except:
            logger.exception("Unable to parse message")
            return

        if self.alarm == None:
            return

        if message['type'] == 'tickle' and msg['subtype'] == 'push':
            now = time.time()
            pushes = self.pb.get_pushes(modified_after=int(now) - 10, limit=1, filter_inactive=True)

            for p in pushes:
                self.pb.dismiss_push(p.get("iden"))
                self.pb.delete_push(p.get("iden"))
                
                if p.get('direction') == 'outgoing' or p.get('dismissed'):
                    continue

                if p.get('sender_email_normalized') in PUSHBULLET_CONTACTS:
                    ret = self.send_command(p.get('body'))

                    if ret:
                        logger.info("From {} ACCEPTED: {}".format(p.get('sender_email_normalized'), p.get('body')))
                    else:
                        logger.warning("From {} UNKNOWN: {}".format(p.get('sender_email_normalized'), p.get('body')))
                else:
                    logger.warning("Command from INVALID SENDER {}: {}".format(p.get('sender_email_normalized'), p.get('body')))

    def unhandled_error(self, error):
        logger.error("{}".format(error))

        try:
            self.terminate()
        except:
            logger.exception("Closing Pushbullet WS")
            
        self.close()

    def send_message(self, msg, dstchat=None):    
        for chat in self.pb.chats:
            if chat.email in PUSHBULLET_CONTACTS:
                try:
                    self.pb.push_note("paradox", msg, chat=chat)
                except:
                    logger.exception("Sending message")

    def send_command(self, message):
        """Handle message received from the MQTT broker"""
        """Format TYPE LABEL COMMAND """
        tokens = message.split(" ")

        if len(tokens) != 3:
            logger.warning("Message format is invalid")
            return

        if self.alarm == None:
            logger.error("No alarm registered")
            return

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self.normalize_payload(tokens[2])
        
        # Process a Zone Command
        if element_type == 'zone':
            if command not in ['bypass', 'clear_bypass']:
                logger.error("Invalid command for Zone {}".format(command))
                return

            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))

        # Process a Partition Command
        elif element_type == 'partition':
            if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
                logger.error(
                    "Invalid command for Partition {}".format(command))
                return

            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))
       
        # Process an Output Command
        elif element_type == 'output':
            if command not in ['on', 'off', 'pulse']:
                logger.error("Invalid command for Output {}".format(command))
                return

            if not self.alarm.control_output(element, command):
                logger.warning(
                    "Output command refused: {}={}".format(element, command))
        else:
            logger.error("Invalid control property {}".format(element))


    def normalize_payload(self, message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None

    def event(self, raw):
        """Handle Live Event"""
        #logger.debug("Live Event: raw={}".format(raw))

        # TODO Improve message display
        if raw['type'] == 'Partition' or raw['type'] == 'System' or raw['type'] == 'Trouble':
            self.send_message(json.dumps(raw))
        

    def change(self, element, label, property, value):
        """Handle Property Change"""
        #logger.debug("Property Change: element={}, label={}, property={}, value={}".format(
        #    element,
        #    label,
        #    property,
        #    value))
        
        # TODO Improve message display
        if element == 'partition' or element == 'system' or element == 'trouble':
            self.send_message("{} {} {} {}".format(element, label, property, value))

       
    def set_alarm(self, alarm):
        self.alarm = alarm

class PushBulletInterface():
    """Interface Class using Pushbullet"""

    def __init__(self):        
        self.pb = None
        self.pb_ws = None
        self.alarm = None

    def set_alarm(self, alarm):
        self.alarm = alarm


    def start(self):
        """Connect to the Pushbullet Server"""

        logger.info("Starting Pushbullet Interface")
        try:
            self.pb_ws = PushBulletWSClient('wss://stream.pushbullet.com/websocket/{}'.format(PUSHBULLET_KEY))
            self.pb_ws.init()
            self.pb_ws.connect()

            return True
        except:
            logger.exception("PB")
        return False
    
    def set_alarm(self, alarm):
        self.pb_ws.set_alarm(alarm)

    def stop(self):
        """ Stops the Pushbullet interface"""
        self.pb_ws.terminate()
    
    def event(self, raw):
        self.pb_ws.event(raw)

    def change(self, element, label, property, value):
        self.pb_ws.change(element, label, property, value)
