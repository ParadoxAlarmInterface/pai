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


def main():
    logger.info("Starting Paradox Alarm Interface")
    logger.info("Console Log level set to {}".format(LOGGING_LEVEL_CONSOLE))
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

    # Load an interface for exposing data and accepting commands
    if MQTT_HOST != "":
        logger.info("Using MQTT Interface")
        from mqtt_interface import MQTTInterface
        interface = MQTTInterface()
        interface.start()
    else:
        logger.error("No Interface specified")
        sys.exit(-1)

    logger.info("Starting...")
    # Start interacting with the alarm
    while True:
        try:
            alarm = Paradox(connection=connection, interface=interface)
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
