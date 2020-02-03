import logging
from os import path

from paradox.config import config

config.load(path.join(path.dirname(__file__), 'pai.conf'))


def configure_logger():
    FORMAT = '%(asctime)s - %(levelname)-8s - %(threadName)-10s - %(name)s - %(message)s'
    logger = logging.getLogger('PAI')
    logconsole_handler = logging.StreamHandler()
    logconsole_handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(logconsole_handler)

    logger.setLevel(logging.DEBUG)


configure_logger()
