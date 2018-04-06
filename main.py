from paradox import Paradox
import logging
import sys
import time
import config_defaults

def main():
    logger = logging.getLogger('paradox')
    
    # Load default config and then user config (if available)
    global_config = config_defaults
    try:
        import config
        global_config = config
        logger.info("Using user config")
    except:
        logger.info("Using default config")

    # Load a connection to the alarm
    if global_config.CONNECTION_TYPE == "Serial":
        from serial_connection import SerialCommunication

        connection = SerialCommunication(port=global_config.SERIAL_PORT)
        if not connection.connect():
            logger.error("Unable to open serial port: {}".format(global_config.SERIAL_PORT))
            sys.exit(-1)
    else:
        logger.error("Invalid connection type: {}".format(global_config.CONNECTION_TYPE))
        sys.exit(-1)

    # Load an interface for exposing data and accepting commands
    if global_config.MQTT_HOST != "":
        from mqtt_interface import MQTTInterface
        interface = MQTTInterface(global_config)
        interface.start()
    else:
        logger.error("No Interface specified")
        sys.exit(-1)
    
    # Start interacting with the alarm
    try:
        alarm = Paradox(connection=connection, interface=interface, config=global_config)
        alarm.connect()
        alarm.loop()
    except:
        logger.exception("Closing")
        connection.close()
        interface.stop()
        logger.info("Exit")

if __name__ == '__main__':
    main()


