#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "João Paulo Barraca"
__copyright__ = "Copyright 2018, João Paulo Barraca"
__credits__ = ["Tihomir Heidelberg", "Louis Rossouw"]
__license__ = "EPL"
__version__ = "0.1"
__maintainer__ = "João Paulo Barraca"
__email__ = "jpbarraca@gmail.com"
__status__ = "Beta"

import logging
import sys
import time
from config_defaults import *
from config import *

FORMAT = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'

logger = logging.getLogger('PAI')
logger.setLevel(LOGGING_LEVEL_CONSOLE)

if LOGGING_FILE is not None:
    logfile_handler = logging.FileHandler(LOGGING_FILE)
    logfile_handler.setLevel(LOGGING_LEVEL_FILE)
    logfile_handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logfile_handler)

logconsole_handler = logging.StreamHandler()
logconsole_handler.setLevel(LOGGING_LEVEL_CONSOLE)
logconsole_handler.setFormatter(logging.Formatter(FORMAT))
logger.addHandler(logconsole_handler)

from paradox import Paradox

class InterfaceManager():
    def __init__(self):
        self.interfaces = []

    def register(self, name, object, initial=False):
        logger.debug("Registering Interface {}".format(name))

        self.interfaces.append(dict(name=name,object=object,initial=initial))
        try:
            object.set_notify(self)
        except:
            logger("Error registering interface {}".format(name))

    def event(self, raw):
        for interface in self.interfaces:
            try:
                interface['object'].event(raw)
            except:
                logger.exception("Error dispatching event to interface {}".format(interface['name']))

    def change(self, element, label, property, value, initial=False):
        for interface in self.interfaces:
            
            if not interface['initial'] and initial:
                continue

            try:
                interface['object'].change(element, label, property, value)
            except:
                logger.exception("Error dispatching change to interface {}".format(interface['name']))
    
    def notify(self, sender, message, level=logging.INFO):
        for interface in self.interfaces:
            try:
                if sender != interface['name']:
                    interface['object'].notify(sender, message, level)
            except:
                logger.exception("Error dispatching notification to interface {}".format(interface['name']))
                
    def stop(self):
        logger.debug("Stopping all interfaces")
        for interface in self.interfaces:
            try:
                logger.debug("\t{}".format(interface['name']))
                interface['object'].stop()
            except:
                logger.exception("Error stoping interface {}".format(interface['name']))
        logger.debug("All Interfaces stopped")

    def set_alarm(self, alarm):
        for interface in self.interfaces:
            try:
                interface['object'].set_alarm(alarm)
            except:
                logger.exception("Error adding alarm to interface {}".format(interface['name']))



def main():
    logger.info("Starting Paradox Alarm Interface")
    logger.info("Console Log level set to {}".format(LOGGING_LEVEL_CONSOLE))

    interface_manager = InterfaceManager()
    
    # Load GSM service
    if GSM_ENABLE:
        try:
            logger.info("Using GSM Interface")
            from gsm_interface import GSMInterface
            interface = GSMInterface()
            interface.start()
            interface_manager.register(interface.name, interface)
        except:
            logger.exception("Unable to start GSM Interface")

    # Load Signal service
    if SIGNAL_ENABLE:
        try:
            logger.info("Using Signal Interface")
            from signal_interface import SignalInterface
            interface = SignalInterface()
            interface.start()
            interface_manager.register(interface.name, interface)
        except:
            logger.exception("Unable to start Signal Interface")
    
    # Load an interface for exposing data and accepting commands
    if MQTT_ENABLE:
        try:
            logger.info("Using MQTT Interface")
            from mqtt_interface import MQTTInterface
            interface = MQTTInterface()
            interface.start()
            interface_manager.register(interface.name, interface, initial=True)
        except:
            logger.exception("Unable to start MQTT Interface")

    # Load Pushbullet service
    if PUSHBULLET_ENABLE:
        try:
            logger.info("Using Pushbullet Interface")
            from pushbullet_interface import PushBulletInterface
            interface = PushBulletInterface()
            interface.start()
            interface_manager.register(interface.name, interface)
        except:
            logger.exception("Unable to start Pushbullet Interface")
   
     # Load IP Interface
    if IP_INTERFACE_ENABLE:
        try:
             logger.info("Using IP Interface")
             from ip_interface import IPInterface
             interface = IPInterface()
             interface.start()
             interface_manager.register(interface.name, interface)
        except:
             logger.exception("Unable to start IP Interface")

    time.sleep(1)

    # Load a connection to the alarm
    if CONNECTION_TYPE == "Serial":
        logger.info("Using Serial Connection")
        from serial_connection import SerialCommunication

        connection = SerialCommunication(port=SERIAL_PORT)
        if not connection.connect():
            logger.error("Unable to open serial port: {}".format(SERIAL_PORT))
            sys.exit(-1)
    if CONNECTION_TYPE == 'IP':
        logger.info("Using IP Connection")
        from ip_connection import IPConnection

        connection = IPConnection(host=IP_CONNECTION_HOST, port=IP_CONNECTION_PORT, password=IP_CONNECTION_PASSWORD)
        if not connection.connect():
            logger.error("Unable to open IP Connection with: {}".format(IP_CONNECTION_HOST))
            sys.exit(-1)
    else:
        logger.error("Invalid connection type: {}".format(CONNECTION_TYPE))
        sys.exit(-1)


    logger.info("Starting...")
    # Start interacting with the alarm
    stop = False
    while True:
        try:
            alarm = Paradox(connection=connection, interface=interface_manager)
            alarm.disconnect()
            if alarm.connect():
                interface_manager.set_alarm(alarm)
                #interface_manager.notify("PAI", "Paradox Alarm Interface is active", logging.INFO)
                alarm.loop()
                break
            else:
                logger.error("Unable to connect to alarm")
                break

            time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Exit start")
            stop = True
            alarm.disconnect()
            break

        except:
            if not stop:
                logger.exception("Restarting")
                time.sleep(1)
    
    interface_manager.stop()
    logger.info("Good bye!")



if __name__ == '__main__':
    main()
