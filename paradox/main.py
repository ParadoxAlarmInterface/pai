import asyncio
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler

from paradox import VERSION
from paradox.config import config as cfg
from paradox.exceptions import PAICriticalException
from paradox.interfaces.interface_manager import InterfaceManager
from paradox.lib.encodings import register_encodings
from paradox.paradox import Paradox

alarm = None
interface_manager = None

logger = logging.getLogger("PAI")


def get_format(level):
    if level <= logging.DEBUG:
        return (
            "%(asctime)s - %(levelname)-8s - %(threadName)-10s - %(name)s - %(message)s"
        )
    else:
        return "%(asctime)s - %(levelname)-8s - %(name)s - %(message)s"


def configure_logger(logger):
    logger_level = cfg.LOGGING_LEVEL_CONSOLE

    if cfg.LOGGING_FILE:
        logfile_handler = RotatingFileHandler(
            cfg.LOGGING_FILE,
            mode="a",
            maxBytes=cfg.LOGGING_FILE_MAX_SIZE * 1024 * 1024,
            backupCount=cfg.LOGGING_FILE_MAX_FILES,
            encoding=None,
            delay=0,
        )

        logfile_handler.setLevel(cfg.LOGGING_LEVEL_FILE)
        logfile_handler.setFormatter(logging.Formatter(get_format(logger_level)))
        logger.addHandler(logfile_handler)
        logger_level = min(logger_level, cfg.LOGGING_LEVEL_FILE)

    logconsole_handler = logging.StreamHandler()
    logconsole_handler.setLevel(cfg.LOGGING_LEVEL_CONSOLE)
    logconsole_handler.setFormatter(logging.Formatter(get_format(logger_level)))
    logger.addHandler(logconsole_handler)

    logger.setLevel(logger_level)


async def exit_handler(signame=None):
    global alarm, interface_manager

    if signame is not None:
        logger.info(f"Captured signal {signame}. Exiting")

    if alarm:
        await alarm.disconnect()
        alarm = None

    if interface_manager:
        interface_manager.stop()
        interface_manager = None

    logger.info("Good bye!")


async def run_loop():
    retry = 1
    while alarm is not None:
        logger.info("Starting...")
        retry_time_wait = 2 ^ retry
        retry_time_wait = 30 if retry_time_wait > 30 else retry_time_wait

        try:
            if await alarm.full_connect():
                retry = 1
                await alarm.loop()
            else:
                logger.error("Unable to connect to alarm")

            if alarm:
                await asyncio.sleep(retry_time_wait)
        except ConnectionError as e:  # Connection to IP Module or MQTT lost
            logger.error("Connection to panel lost: %s. Restarting" % str(e))
            await asyncio.sleep(retry_time_wait)
        except OSError:  # Connection to IP Module or MQTT lost
            logger.exception("Restarting")
            await asyncio.sleep(retry_time_wait)
        except PAICriticalException:
            logger.exception("PAI Critical exception. Stopping PAI")
            break
        except (KeyboardInterrupt, SystemExit):
            break  # break exits the retry loop
        except:
            logger.exception("Restarting")
            await asyncio.sleep(retry_time_wait)

        retry += 1

    if alarm:
        await exit_handler()


def main(args):
    global alarm, interface_manager

    time.tzset()
    if "config" in args and args.config is not None:
        import os

        config_file = os.path.abspath(args.config)
        cfg.load(config_file)
    else:
        cfg.load()

    configure_logger(logger)

    logger.info(f"Starting Paradox Alarm Interface {VERSION}")
    logger.info(f"Config loaded from {cfg.CONFIG_FILE_LOCATION}")

    logger.info(f"Console Log level set to {cfg.LOGGING_LEVEL_CONSOLE}")

    # Registering additional encodings
    register_encodings()

    # Start interacting with the alarm
    alarm = Paradox()
    loop = asyncio.get_event_loop()
    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame)
        loop.add_signal_handler(
            sig, lambda: asyncio.ensure_future(exit_handler(signame))
        )

    interface_manager = InterfaceManager(alarm, config=cfg)
    interface_manager.start()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_loop())

    sys.exit(0)
