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
from config import user as cfg

FORMAT = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'

logger = logging.getLogger('PAI')
logger.setLevel(cfg.LOGGING_LEVEL_CONSOLE)

if cfg.LOGGING_FILE is not None:
    logfile_handler = logging.FileHandler(cfg.LOGGING_FILE)
    logfile_handler.setLevel(cfg.LOGGING_LEVEL_FILE)
    logfile_handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logfile_handler)

logconsole_handler = logging.StreamHandler()
logconsole_handler.setLevel(cfg.LOGGING_LEVEL_CONSOLE)
logconsole_handler.setFormatter(logging.Formatter(FORMAT))
logger.addHandler(logconsole_handler)

from paradox.paradox import Paradox
from paradox.interfaces.interface_manager import InterfaceManager


def main():
    logger.info("Starting Paradox Alarm Interface")
    logger.info("Console Log level set to {}".format(cfg.LOGGING_LEVEL_CONSOLE))

    interface_manager = InterfaceManager(config=cfg)
    interface_manager.start()

    time.sleep(1)

    # Load a connection to the alarm
    if cfg.CONNECTION_TYPE == "Serial":
        logger.info("Using Serial Connection")
        from paradox.connections.serial_connection import SerialCommunication

        connection = SerialCommunication(port=cfg.SERIAL_PORT)
    elif cfg.CONNECTION_TYPE == 'IP':
        logger.info("Using IP Connection")
        from paradox.connections.ip_connection import IPConnection

        connection = IPConnection(host=cfg.IP_CONNECTION_HOST, port=cfg.IP_CONNECTION_PORT, password=cfg.IP_CONNECTION_PASSWORD)
    else:
        logger.error("Invalid connection type: {}".format(cfg.CONNECTION_TYPE))
        sys.exit(-1)

    # Start interacting with the alarm
    alarm = Paradox(connection=connection, interface=interface_manager)
    retry = 1
    while True:
        logger.info("Starting...")
        retry_time_wait = 2 ^ retry
        retry_time_wait = 30 if retry_time_wait > 30 else retry_time_wait

        try:
            alarm.disconnect()
            if alarm.connect():
                retry = 1
                interface_manager.set_alarm(alarm)
                alarm.loop()
            else:
                logger.error("Unable to connect to alarm")

            time.sleep(retry_time_wait)
        except (ConnectionError, OSError):  # Connection to IP Module or MQTT lost
            logger.exception("Restarting")
            time.sleep(retry_time_wait)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Exit start")
            if alarm:
                alarm.disconnect()
            break  # break exits the retry loop

        except Exception:
            logger.exception("Restarting")
            time.sleep(retry_time_wait)

        retry += 1

    interface_manager.stop()
    logger.info("Good bye!")
