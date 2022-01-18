import logging
from os import path

from paradox.config import config
from paradox.lib.encodings import register_encodings

config.load(path.join(path.dirname(__file__), "pai.conf"))


def _configure_logger(name: str, handler: logging.Handler):
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def configure_logger():
    FORMAT = (
        "%(asctime)s - %(levelname)-8s - %(threadName)-10s - %(name)s - %(message)s"
    )
    logging.captureWarnings(True)

    logconsole_handler = logging.StreamHandler()
    logconsole_handler.setFormatter(logging.Formatter(FORMAT))

    _configure_logger('PAI', logconsole_handler)
    _configure_logger('py', logconsole_handler)


configure_logger()
register_encodings()
