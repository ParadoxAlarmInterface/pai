from paradox import Paradox
import logging
import sys
import time
from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)

def main():    
    logger.setLevel(LOGGING_LEVEL_CONSOLE)
    
    # Load a connection to the alarm
    if CONNECTION_TYPE == "Serial":
        from serial_connection import SerialCommunication

        connection = SerialCommunication(port=SERIAL_PORT)
        if not connection.connect():
            logger.error("Unable to open serial port: {}".format(SERIAL_PORT))
            sys.exit(-1)
    else:
        logger.error("Invalid connection type: {}".format(CONNECTION_TYPE))
        sys.exit(-1)

    # Load an interface for exposing data and accepting commands
    if MQTT_HOST != "":
        from mqtt_interface import MQTTInterface
        interface = MQTTInterface()
        interface.start()
    else:
        logger.error("No Interface specified")
        sys.exit(-1)
    
    # Start interacting with the alarm
    while True:    
        try:
            alarm = Paradox(connection=connection, interface=interface)
            if alarm.connect():
                interface.set_alarm(alarm)
                alarm.loop()
        except (KeyboardInterrupt, SystemExit):
            break

        except:
            logger.exception("Restarting")
            time.sleep(1)
    
    connection.close()
    interface.stop()
    logger.info("Exit")

if __name__ == '__main__':
    main()


