# -*- coding: utf-8 -*-

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
        self.partitions = dict()
        

    def stop(self):
        """ Stops the Signal Interface Thread"""
        logger.debug("Stopping Signal Interface")
        if self.loop is not None:
            self.stop_running.set()
            self.loop.quit()

        logger.debug("Signal Stopped")

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm
    
    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        return

    def change(self, element, label, property, value):
        """ Enqueues a change """
        return

    def notify(self, source, message, level):
        if source == self.name:
            return
        
        if level < logging.INFO:
            return
        
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))


    def run(self):

        logger.info("Starting Signal Interface")

        bus = SystemBus()

        self.signal = bus.get('org.asamk.Signal')
        self.signal.onMessageReceived = self.handle_message
        self.loop = GLib.MainLoop()
    
        self.timer = GObject.idle_add(self.run_loop)

        logger.debug("Signal Interface Running")
        try:
            self.loop.run()
        
        except (KeyboardInterrupt, SystemExit):
            logger.debug("Signal loop stopping")
            if self.alarm is not None:
                self.loop.quit()
                self.alarm.disconnect()
        except :
            logger.exception("Signal loop")
    
    def run_loop(self):
        try:
            item = self.queue.get(block=True, timeout=1)
            
            if item[1] == 'change':
                self.handle_change(item[2])
            elif item[1] == 'event':
                self.handle_event(item[2])
            elif item[1] == 'notify':
                self.send_message("{}: {}".format(item[2][0], item[2][1]))

        except queue.Empty as e:
            return True
        except:
            logger.exception("loop")

        return True

    def send_message(self, message):
        if self.signal is None:
            logger.warning("Signal not available when sending message")
            return
        try:    
            self.signal.sendMessage(str(message), [], SIGNAL_CONTACTS)
        except:
            logger.exception("Signal send message")

    def handle_message (self, timestamp, source, groupID, message, attachments):
        """ Handle Signal message. It should be a command """

        logger.debug("Received Message {} {} {} {} {}".format(timestamp, message, groupID, message, attachments))

        if self.alarm == None:
            return

        if source in SIGNAL_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("ACCEPTED: {}".format(message))
                self.send_message("ACCEPTED: {}".format(message))
            else:
                logger.warning("REJECTED: {}".format(message))
                self.send_message("REJECTED: {}".format(message))
        else:
            logger.warning("REJECTED: {}".format(message))
            self.send_message("REJECTED: {}".format(message))



    def send_command(self, message):
        """Handle message received from the MQTT broker"""
        """Format TYPE LABEL COMMAND """
        tokens = message.split(" ")

        if len(tokens) != 3:
            logger.warning("Message format is invalid")
            return False

        if self.alarm == None:
            logger.error("No alarm registered")
            return False

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self.normalize_payload(tokens[2].lower())
        
        # Process a Zone Command
        if element_type == 'zone':
            if command not in ['bypass', 'clear_bypass']:
                logger.error("Invalid command for Zone {}".format(command))
                return False

            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))
                return False

        # Process a Partition Command
        elif element_type == 'partition':
            if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
                logger.error(
                    "Invalid command for Partition {}".format(command))
                return False

            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))
                return False

        # Process an Output Command
        elif element_type == 'output':
            if command not in ['on', 'off', 'pulse']:
                logger.error("Invalid command for Output {}".format(command))
                return False

            if not self.alarm.control_output(element, command):
                logger.warning(
                    "Output command refused: {}={}".format(element, command))
                return False
        else:
            logger.error("Invalid control property {}".format(element))
            return False
        
        return True
    

    def handle_notify(self, raw):
        source, message, level = raw

        try:
            self.send_message(message)
        except:
            logger.exception("handle_notify")

    def handle_event(self, raw):
        """Handle Live Event"""
        #logger.debug("Live Event: raw={}".format(raw))

        #m = "{}: {}".format(raw['major'][1], raw['minor'][1])
        major_code = raw['major'][0]
        minor_code = raw['minor'][1]
        
        # Ignore some events

        for ev in SIGNAL_IGNORE_EVENTS:
            if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                return

        if major_code == 29:
            self.send_message("Arming by user {}".format(minor_code))
        elif major_code == 31:
            self.send_message("Disarming by user {}".format(minor_code))
        else:
            self.send_message(str(raw))
        

    def handle_change(self, raw ):
        element, label, property, value = raw
        """Handle Property Change"""
        #logger.debug("Property Change: element={}, label={}, property={}, value={}".format(
        #    element,
        #    label,
        #    property,
        #    value))
        message = "{} {} {} {}".format(element, label, property, value)
        if element == 'partition':
            if element not in self.partitions:
                self.partitions[label] = dict()
            
            self.partitions[label][property] = value

            if property == 'arm_sleep':
                return
            elif property == 'exit_delay' :
                if not value:
                    return
                else:
                    message = "Partition {} in Exit Delay".format(label)
                    if 'arm_sleep' in self.partitions[label] and self.partitions[label]['arm_sleep']:
                        m = ''.join([m, ' (Sleep)'])
            elif property == 'entry_delay' :
                if not value:
                    return
                else:
                    message = "Partition {} in Entry Delay".format(label)
            elif property == 'arm':
                try:
                    if value:
                        message = "Partition {} is Armed".format(label)
                        if 'arm_sleep' in self.partitions[label] and self.partitions[label]['arm_sleep']:
                            m = ''.join([m, ' (Sleep)'])
                    else:
                        message = "Partition {} is Disarmed".format(label)
                except:
                    logger.exception("ARM")

            elif property == 'arm_full':
                return
        elif element == 'zone':
            if property == 'alarm':
                if value:
                    message = "Zone {} is in Alarm".format(label)
                else:
                    message = "Zone {} Alarm cleared".format(label)

        self.send_message(message)


    def normalize_payload(self, message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None

