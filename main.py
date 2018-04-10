import logging
import sys
import time
from config_defaults import *
from config import *

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT)

logger = logging.getLogger('PAI')
logger.setLevel(LOGGING_LEVEL_CONSOLE)

from paradox import Paradox

class InterfaceHandler():
    def __init__(self):
        self.interfaces = []

    def register(self, name, object, initial=False):
        self.interfaces.append(dict(name=name,object=object,initial=initial))

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

def main():
    logger.info("Starting Paradox Alarm Interface")
    logger.info("Console Log level set to {}".format(LOGGING_LEVEL_CONSOLE))

    interface_handler = InterfaceHandler()

    # Load an interface for exposing data and accepting commands
    if MQTT_HOST != "":
        try:
            logger.info("Using MQTT Interface")
            from mqtt_interface import MQTTInterface
            interface = MQTTInterface()
            if interface.start():
                interface_handler.register('mqtt', interface, initial=True)
        except:
            logger.error("Unable to start MQTT Interface")

    # Load Pushbullet service
    if len(PUSHBULLET_SECRET) > 0 and len(PUSHBULLET_CONTACTS) > 0 and len(PUSHBULLET_CONTACTS) > 0:
        try:
            logger.info("Using Pushbullet Interface")
            from pushbullet_interface import PushBulletInterface
            interface = PushBulletInterface()
            if interface.start():
                interface_handler.register('pushbullet', interface, initial=False)
        except:
            logger.exception("Unable to start Pushbullet Interface")

    # Load a connection to the alarm
    if CONNECTION_TYPE == "Serial":
        logger.info("Using Serial Connection")
        from serial_connection import SerialCommunication

        connection = SerialCommunication(port=SERIAL_PORT)
        if not connection.connect():
            logger.error("Unable to open serial port: {}".format(SERIAL_PORT))
            sys.exit(-1)
    else:
        logger.error("Invalid connection type: {}".format(CONNECTION_TYPE))
        sys.exit(-1)


    logger.info("Starting...")
    # Start interacting with the alarm
    while True:
        try:
            alarm = Paradox(connection=connection, interface=interface_handler)
            if alarm.connect():
                interface.set_alarm(alarm)
                alarm.loop()
            else:
                logger.error("Unable to connect to alarm")
                break

            time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Exit start")
            break

        except:
            logger.exception("Restarting")
            time.sleep(1)

    #connection.close()
    interface.stop()
    logger.info("Good bye!")


if __name__ == '__main__':
    main()
