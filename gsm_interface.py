# -*- coding: utf-8 -*-

# GSM interface.
# Only exposes critical status changes and accepts commands
import time
import logging
import datetime
import json

from threading import Thread, Event
from utils import SortableTuple

from config_defaults import *
from config import *
import queue

import serial

logger = logging.getLogger('PAI').getChild(__name__)


class GSMInterface(Thread):
    """Interface Class using GSM"""
    name = 'gsm'

    port = None
    alarm = None
    stop_running = Event()
    thread = None
    loop = None
    notification_handler = None 
    
    def __init__(self):
        Thread.__init__(self)
        
        self.queue = queue.PriorityQueue()
        self.partitions = dict()
        self.stop_running.clear() 

    def stop(self):
        """ Stops the GSM Interface Thread"""
        logger.debug("Stopping GSM Interface")
        self.stop_running.set()
        
        self.port.close()

        logger.debug("GSM Stopped")
        
    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm
    
    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        
        # Fire Alarm and Strobe
        # Special Alarms
        if raw['major'][0] == 37 or \
            (raw['major'][0] == 2 and raw['minor'][0] == 6) or \
            (raw['major'][0] == 40  and raw['minor'][0] in [0,1,2,3,4,5]):

            self.queue.put_nowait(SortableTuple((2, 'event', (raw))))


    def change(self, element, label, property, value):
        """ Enqueues a change """    
        return

    def notify(self, source, message, level):
        if source == self.name:
            return
        
        if level < logging.CRITICAL:
            return
        
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

    def write(self, message):
        self.port.write((message + '\r\n').encode('latin-1'))
        time.sleep(0.1) 
        data = b''
        while self.port.in_waiting > 0:
            data += self.port.read()
        
        data = data.strip().decode('latin-1')
        return data

    def run(self):

        logger.info("Starting GSM Interface")

        try:
            logger.info("Using {} at {} baud".format(GSM_MODEM_PORT, GSM_MODEM_BAUDRATE))
            self.port = serial.Serial(GSM_MODEM_PORT, baudrate=GSM_MODEM_BAUDRATE, timeout=5)

            self.write('AT')
            self.write('ATE0')
            self.write('AT+CMGF=1')
            self.write('AT+CNMI=1,2,0,0,0')
            self.write('AT+CUSD=1,"*111#"')

            logger.info("Started GSM Interface")
            
            while not self.stop_running.isSet():
                try:
                    data = self.port.read(200)
                    if len(data) > 0:
                        tokens = data.decode('latin-1').strip().split('"')
                        for i in range(len(tokens)):
                            tokens[i] = tokens[i].strip()
                        
                        if len(tokens) > 0:
                            if tokens[0] == '+CMT:':
                                source = tokens[1]
                                timestamp = datetime.datetime.strptime(tokens[5].split('+')[0],'%y/%m/%d,%H:%M:%S')
                                message = tokens[6]
                                self.handle_message(timestamp, source, message)
                            elif tokens[0].startswith('+CUSD:'):
                                self.notification_handler.notify(self.name, tokens[1], logging.INFO)
                    else:
                        self.run_loop()

                except:
                    logger.exception("")
        
        except (KeyboardInterrupt, SystemExit):
            logger.debug("GSM loop stopping")
            return

        except :
            logger.exception("GSM loop")
    
    def run_loop(self):
        try:
            item = self.queue.get(block=False, timeout=1)
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
    
    def send_sms(self, dst, message):
        self.write('AT+CMGS="{}"'.format(dst))    
        self.write(message)
        self.write('\x1A\r\n')

    def send_message(self, message):
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return
         
        for dst in GSM_CONTACTS:
           self.send_sms(dst, message)

    def handle_message (self, timestamp, source, message):
        """ Handle GSM message. It should be a command """

        logger.debug("Received Message {} {} {}".format(timestamp, source, message))

        if self.alarm == None:
            return
        
        self.notification_handler.notify(self.name, "{}: {}".format(source, message), logging.INFO)

        if source in GSM_CONTACTS:
            ret = self.send_command(message)

            if ret:
                logger.info("ACCEPTED: {}".format(message))
                self.send_sms(source, "ACCEPTED: {}".format(message))
                self.notification_handler.notify(self.name, "ACCEPTED: {}: {}".format(source, message), logging.INFO)
            else:
                logger.warning("REJECTED: {}".format(message))
                self.send_sms(source, "REJECTED: {}".format(message))
                self.notification_handler.notify(self.name, "REJECTED: {}: {}".format(source, message), logging.INFO)
        else:
            logger.warning("REJECTED: {}".format(message))
            self.notification_handler.notify(self.name, "REJECTED: {}: {}".format(source, message), logging.INFO)


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
        source, message, level = raw
        
        try:
            self.send_message(message)
        except:
            logger.exception("handle_notify")

    def handle_event(self, raw):
        """Handle Live Event"""
        
        # All events are extremelly critical. Make call to get user attention
        
        for contact in GSM_CONTACTS:
            self.write('ATD{}'.format(contact))


    def handle_change(self, raw ):
        """Handle Property Change"""
        return

    def normalize_payload(self, message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None

