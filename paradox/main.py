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
from logging.handlers import RotatingFileHandler
import sys
import time
import signal

from paradox.config import config as cfg


from paradox.paradox import Paradox
from paradox.interfaces.interface_manager import InterfaceManager

alarm = None
interface_manager = None

logger = logging.getLogger('PAI')
FORMAT = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'

def config_logger(logger):
    logger_level = cfg.LOGGING_LEVEL_CONSOLE

    if cfg.LOGGING_FILE is not None:
        logfile_handler = RotatingFileHandler(cfg.LOGGING_FILE, mode='a',
                            maxBytes=cfg.LOGGING_FILE_MAX_SIZE*1024*1024, 
                            backupCount=cfg.LOGGING_FILE_MAX_FILES,
                            encoding=None, delay=0)

        logfile_handler.setLevel(cfg.LOGGING_LEVEL_FILE)
        logfile_handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(logfile_handler)
        logger_level = min(logger_level, cfg.LOGGING_LEVEL_FILE)

    logconsole_handler = logging.StreamHandler()
    logconsole_handler.setLevel(cfg.LOGGING_LEVEL_CONSOLE)
    logconsole_handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logconsole_handler)

    logger.setLevel(logger_level)

def exit_handler(signal=None, frame=None):
    global alarm, interface_manager
    
    if alarm:
        alarm.disconnect()
        alarm = None

    if interface_manager:
        interface_manager.stop()
        interface_manager = None

    time.sleep(1)
    
    logger.info("Good bye!")
    sys.exit(0)


def main(args):
    global alarm, interface_manager
    
    if 'config' in args and args.config is not None:
        import os
        config_file = os.path.abspath(args.config)
        cfg.load(config_file)
    else:
        cfg.load()

    config_logger(logger)

    logger.info("Starting Paradox Alarm Interface")
    logger.info("Console Log level set to {}".format(cfg.LOGGING_LEVEL_CONSOLE))

    interface_manager = InterfaceManager(config=cfg)
    interface_manager.start()

    time.sleep(1)

    # Load a connection to the alarm
    if cfg.CONNECTION_TYPE == "Serial":
        logger.info("Using Serial Connection")
        from paradox.connections.serial_connection import SerialCommunication

        connection = SerialCommunication(port=cfg.SERIAL_PORT, baud=cfg.SERIAL_BAUD)
    elif cfg.CONNECTION_TYPE == 'IP':
        logger.info("Using IP Connection")
        from paradox.connections.ip_connection import IPConnection

        connection = IPConnection(host=cfg.IP_CONNECTION_HOST, port=cfg.IP_CONNECTION_PORT, password=cfg.IP_CONNECTION_PASSWORD)
    else:
        logger.error("Invalid connection type: {}".format(cfg.CONNECTION_TYPE))
        sys.exit(-1)

    signal.signal(signal.SIGINT, exit_handler)

    # Start interacting with the alarm
    alarm = Paradox(connection=connection)
    interface_manager.set_alarm(alarm)
    retry = 1
    while True:
        logger.info("Starting...")
        retry_time_wait = 2 ^ retry
        retry_time_wait = 30 if retry_time_wait > 30 else retry_time_wait

        try:
            if alarm.connect():
                retry = 1
                alarm.loop()
            else:
                logger.error("Unable to connect to alarm")

            time.sleep(retry_time_wait)
        except ConnectionError as e:  # Connection to IP Module or MQTT lost
            logger.error("Connection to panel lost: %s. Restarting" % str(e))
            time.sleep(retry_time_wait)

        except OSError:  # Connection to IP Module or MQTT lost
            logger.exception("Restarting")
            time.sleep(retry_time_wait)

        except (KeyboardInterrupt, SystemExit):
            break  # break exits the retry loop

        except Exception:
            logger.exception("Restarting")
            time.sleep(retry_time_wait)

        retry += 1
    
    exit_handler()

