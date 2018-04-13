# Signal interface.
# Only exposes critical status changes and accepts commands
from pydbus import SystemBus

from gi.repository import GLib
from gi.repository import GObject

import time
import logging
import datetime
import json

from threading import Thread, Event
from utils import SortableTuple

from config_defaults import *
from config import *
import queue

logger = logging.getLogger('PAI').getChild(__name__)


class SignalInterface(Thread):
    """Interface Class using Signal"""
    name = 'signal'

    signal = None
    alarm = None
    stop_running = Event()
    thread = None
    loop = None
    
    
    def __init__(self):
        Thread.__init__(self)
        
        self.queue = queue.PriorityQueue()


    def stop(self):
        """ Stops the Signal Interface Thread"""
        logger.debug("Stopping Signal Interface")
        self.queue.put_nowait(SortableTuple((0, 'command', 'stop')))

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm
    
    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        # TODO Improve message display
       
        # Open Cloze
        if raw['major'][0] in (0, 1):
            return
        
        # Software Log on
        if raw['major'][0] == 48 and raw['minor'][0] == 2:
            return

        # Squawk on off
        if raw['major'][0] == 2 and raw['minor'][0] in (8, 9):
            return

        # Bell Squawk
        if raw['major'][0] == 3 and raw['minor'][0] in (3, ):
            return

        # Arming Through Winload
        if raw['major'][0] == 30 and raw['minor'][0] == 5:
            return

        # Disarming Through Winload
        if raw['major'][0] == 34 and raw['minor'][0] == 1:
            return

        self.queue.put_nowait(SortableTuple((2, 'event', raw)))

    def change(self, element, label, property, value):
        """ Enqueues a change """
        
        if element == 'zone':
            return

        self.queue.put_nowait(SortableTuple((2, 'change', (element, label, property, value))))

    def notify(self, source, message):
        if source == self.name:
            return

        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message))))


    def run(self):

        logger.info("Starting Signal Interface")

        bus = SystemBus()

        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self.handle_message
        self.loop = GLib.MainLoop()

        self.send_message("Active")
        self.timer = GObject.idle_add(self.run_loop)

        try:
            logger.debug("Signal Interface Running")
            self.loop.run()

        except (KeyboardInterrupt, SystemExit):
            logger.info("Exit start")
            self.stop_running.set()
            self.loop.quit()
            self.stop()
        except:
            logger.exception("signal")
    
    def run_loop(self):
        try:
            item = self.queue.get(block=True, timeout=1)
            if item[1] == 'change':
                self.handle_change(item[2])
            elif item[1] == 'event':
                self.handle_event(item[2])
            elif item[1] == 'notify':
                self.send_message("{}: {}".format(item[2][0], item[2][1]))
            elif item[1] == 'command':
                if item[2] == 'stop':
                    self.loop.quit()
        except:
            pass

        return True

    def send_message(self, message):
        if self.signal is None:
            logger.warning("Signal not available when sending message")
            return
        
        for contact in SIGNAL_CONTACTS:
            self.signal.sendMessage(str(message), [], [contact])


    def handle_message (timestamp, source, groupID, message, attachments):
        """ Handle Signal message. It should be a command """

        logger.debug("Received Message {}".format(message))
        try:
            message = json.loads(str(message))
        except:
            logger.exception("Unable to parse message")
            return

        if self.alarm == None:
            return

        if source in SIGNAL_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("From {} ACCEPTED: {}".format(p.get('sender_email_normalized'), message))
            else:
                logger.warning("From {} UNKNOWN: {}".format(p.get('sender_email_normalized'), message))
        else:
            logger.warning("Command from INVALID SENDER {}: {}".format(p.get('sender_email_normalized'), message))



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

    

    def handle_notify(self, raw):
        source, message = raw

        self.send_message(message)


    def handle_event(self, raw):
        """Handle Live Event"""
        #logger.debug("Live Event: raw={}".format(raw))

        m = "{}: {}".format(raw['major'][1], raw['minor'][1])

        self.send_message(m)
        

    def handle_change(self, raw ):
        element, label, property, value = raw
        """Handle Property Change"""
        #logger.debug("Property Change: element={}, label={}, property={}, value={}".format(
        #    element,
        #    label,
        #    property,
        #    value))
        
 
        self.send_message("{} {} {} {}".format(element, label, property, value))




    def normalize_payload(self, message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None

