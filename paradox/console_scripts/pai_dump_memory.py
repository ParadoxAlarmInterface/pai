#!/usr/bin/env python3

__author__ = "João Paulo Barraca, Jevgeni Kiski"
__copyright__ = "Copyright 2018-2019, João Paulo Barraca"
__credits__ = ["Tihomir Heidelberg", "Louis Rossouw"]
__license__ = "EPL"
__maintainer__ = "João Paulo Barraca"
__email__ = "jpbarraca@gmail.com"
__status__ = "Beta"

import argparse
import asyncio
import logging
import os
import sys

from paradox.config import config as cfg
from paradox.lib import help
from paradox.lib.encodings import register_encodings
from paradox.paradox import Paradox

if sys.version_info < (3, 6,):
    print(
        "You are using Python %s.%s, but PAI requires at least Python 3.6"
        % (sys.version_info[0], sys.version_info[1])
    )
    sys.exit(-1)

logger = logging.getLogger("PAI").getChild(__name__)


async def dump_memory(file, memory):
    alarm = Paradox()
    if not await alarm.connect():
        logger.error("Failed to connect")

    await alarm.dump_memory(file, memory)
    await alarm.disconnect()


def main():
    parser = argparse.ArgumentParser()
    types = parser.add_mutually_exclusive_group(required=True)
    types.add_argument(
        "-r", "--ram", dest="type", action="store_const", help="Dump RAM", const="ram"
    )
    types.add_argument(
        "-e",
        "--eeprom",
        dest="type",
        action="store_const",
        help="Dump EEPROM",
        const="eeprom",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=argparse.FileType("wb"),
        default=sys.stdout,
        help="Dump to file. Default stdout",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="specify path to an alternative configuration file",
    )

    args = parser.parse_args()

    if "config" in args and args.config is not None:
        config_file = os.path.abspath(args.config)
        cfg.load(config_file)
    else:
        cfg.load()

    # Registering additional encodings
    register_encodings()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(dump_memory(args.file, args.type))


if __name__ == "__main__":
    try:
        main()
    except ImportError as error:
        help.import_error_help(error)
