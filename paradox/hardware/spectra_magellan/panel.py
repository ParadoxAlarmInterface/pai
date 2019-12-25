# -*- coding: utf-8 -*-

import asyncio
import binascii
import inspect
import logging
from typing import Optional

from construct import Construct, Container, ChecksumError

from paradox.config import config as cfg
from paradox.exceptions import StatusRequestException
from . import parsers
from .event import event_map
from .property import property_map
from ..panel import Panel as PanelBase

logger = logging.getLogger('PAI').getChild(__name__)

PARTITION_ACTIONS = dict(arm=0x04, disarm=0x05, arm_stay=0x01, arm_sleep=0x03,  arm_stay_stayd=0x06, arm_sleep_stay=0x07, disarm_all=0x08)
ZONE_ACTIONS = dict(bypass=0x10, clear_bypass=0x10)
PGM_ACTIONS = dict(on_override=0x30, off_override=0x31, on=0x32, off=0x33, pulse=0)


class Panel(PanelBase):

    event_map = event_map
    property_map = property_map
    max_eeprom_response_data_length = 32

    mem_map = {
        "status_base1": 0x8000,
        "status_base2": 0x1fe0,
        "definitions": {
            "zone": {
                "addresses": [
                    range(0x730, 0x800, 0x03)
                ]
            }
        },
        "labels": {
            "zone": {"label_offset": 0, "addresses": [range(0x010, 0x210, 0x10)]},
            "pgm": {"label_offset": 0, "addresses": [range(0x210, 0x310, 0x10)], "template": {
                "on": False,
                "pulse": False}
                    },
            "partition": {"label_offset": 0, "addresses": [range(0x310, 0x330, 0x10)]},
            "user": {"label_offset": 0, "addresses": [range(0x330, 0x530, 0x10)]},
            "bus-module": {"label_offset": 0, "addresses": [range(0x530, 0x620, 0x10)]},
            "repeater": {"label_offset": 0, "addresses": [range(0x620, 0x640, 0x10)]},
            "keypad": {"label_offset": 0, "addresses": [range(0x640, 0x6c0, 0x10)]},
            "site": {"label_offset": 0, "addresses": [range(0x6c0, 0x6d0, 0x10)]},
            "siren": {"label_offset": 0, "addresses": [range(0x6d0, 0x700, 0x10)]}
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_power_update = 0

    async def dump_memory(self):
        """
        Dumps EEPROM and RAM memory to files
        :return:
        """
        await self.dump_memory_to_file('eeprom.bin', range(0, 0x0fff, 32))
        await self.dump_memory_to_file('ram.bin', range(0, 9), ram=True)

    async def dump_memory_to_file(self, file, range_, ram=False):
        mem_type = "RAM" if ram else "EEPROM"
        logger.info("Dump " + mem_type)

        with open(file, 'wb') as fh:
            for address in range_:
                if ram:
                    args = dict(address=address + self.mem_map['status_base1'])
                else:
                    args = dict(address=address)

                logger.info("Dumping %s: address %x" % (mem_type, address))

                reply = await self.core.send_wait(
                    parsers.ReadEEPROM, args,
                        reply_expected=lambda m: m.fields.value.po.command == 0x05 and m.fields.value.address == address)

                if reply is None:
                    logger.error("Could not read %s: address %x" % (mem_type, address))
                    return

                data = reply.fields.value.data

                fh.write(data)

    def get_message(self, name: str) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(parsers))
            if name in clsmembers:
                return clsmembers[name]
        except ResourceWarning:
            pass

        return super(Panel, self).get_message(name)

    def parse_message(self, message: bytes, direction='topanel') -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel, self).parse_message(message, direction)
            if parent_parsed:
                return parent_parsed

            if direction == 'topanel':
                if message[0] == 0x70 and message[-5] != 0:
                    return parsers.CloseConnection.parse(message)
                elif message[0] == 0x00:
                    return parsers.InitializeCommunication.parse(message)
                elif message[0] == 0x30:
                    return parsers.SetTimeDate.parse(message)
                elif message[0] == 0x40:
                    return parsers.PerformAction.parse(message)
                elif message[0] == 0x50 and message[2] < 0x80:
                    return parsers.ReadEEPROM.parse(message)
            
            else:
                if message[0] == 0x10:
                    return parsers.InitializeCommunicationResponse.parse(message)
                elif message[0] >> 4 == 0x7 and message[-5] == 0:
                    return parsers.ErrorMessage.parse(message)
                elif message[0] >> 4 == 0x03:
                    return parsers.SetTimeDateResponse.parse(message)
                elif message[0] >> 4 == 0x04:
                    return parsers.PerformActionResponse.parse(message)
                elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                    return parsers.ReadStatusResponse.parse(message)
                elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                    return parsers.ReadEEPROMResponse.parse(message)

            #        elif message[0] == 0x60 and message[2] < 0x80:
            #            return WriteEEPROM.parse(message)
            #        elif message[0] >> 4 == 0x06 and message[2] < 0x80:
            #            return WriteEEPROMResponse.parse(message)
                elif message[0] >> 4 == 0x0e:
                    return parsers.LiveEvent.parse(message)

        except ChecksumError as e:
            logger.error("ChecksumError %s, message: %s" % (str(e), binascii.hexlify(message)))
        except Exception:
            logger.exception("Exception parsing message: %s" % (binascii.hexlify(message)))
        return None

    async def initialize_communication(self, reply: Container, password):
        encoded_password = self.encode_password(password)

        args = dict(product_id=reply.fields.value.product_id,
                    firmware=reply.fields.value.firmware,
                    panel_id=reply.fields.value.panel_id,
                    pc_password=encoded_password,
                    user_code=0x000000,
                    _not_used1=0x19,
                    source_id=0x02
                    )

        logger.info("Initializing communication")
        reply = await self.core.send_wait(parsers.InitializeCommunication, args=args, reply_expected=0x10)

        if reply is None:
            logger.error("Initialization Failed")
            return False

        if reply.fields.value.po.command == 0x10:
            logger.info("Authentication Success")
            return True
        elif reply.fields.value.po.command == 0x70 or reply.fields.value.po.command == 0x00:
            logger.error("Authentication Failed. Wrong Password?")
            return False

    @staticmethod
    def _request_status_reply_check(message: Container, address: int):
        mvars = message.fields.value

        if (
                mvars.po.command == 0x05
                and mvars.address == address
        ):
            return True

        return False

    async def request_status(self, i: int):
        args = dict(address=self.mem_map['status_base1'] + i)
        reply = await self.core.send_wait(parsers.ReadEEPROM, args, reply_expected=lambda m: self._request_status_reply_check(m, i))
        if reply is not None:
            logger.debug("Received status response: %d" % i)
            return self.handle_status(reply, parsers.RAMDataParserMap)
        else:
            raise StatusRequestException("No reply to status request: %d" % i)

    async def control_zones(self, zones: list, command: str) -> bool:
        """
        Control zones
        :param list zones: a list of zones
        :param str command: textual command
        :return: True if we have at least one success
        """
        if command not in ZONE_ACTIONS:
            return False

        accepted = False

        for zone in zones:
            args = dict(action=ZONE_ACTIONS[command], argument=(zone - 1))
            reply = await self.core.send_wait(parsers.PerformAction, args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        return accepted

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """
        Control Partitions
        :param list partitions: a list of partitions
        :param str command: textual command
        :return: True if we have at least one success
        """
        if command not in PARTITION_ACTIONS:
            return False

        accepted = False

        for partition in partitions:
            args = dict(action=PARTITION_ACTIONS[command], argument=(partition - 1))
            reply = await self.core.send_wait(parsers.PerformAction, args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        return accepted

    async def control_outputs(self, outputs, command) -> bool:
        """
        Control PGM
        :param list outputs: a list of pgms
        :param str command: textual command
        :return: True if we have at least one success
        """
        if command not in PGM_ACTIONS:
            return False

        accepted = False

        for output in outputs:
            if command == 'pulse':
                args = dict(action=PGM_ACTIONS['on'], argument=(output - 1))
                reply = await self.core.send_wait(parsers.PerformAction, args, reply_expected=0x04)
                if reply is None:
                    continue

                await asyncio.sleep(cfg.OUTPUT_PULSE_DURATION)
                args = dict(action=PGM_ACTIONS['off'], argument=(output - 1))
                reply = await self.core.send_wait(parsers.PerformAction, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True
            else:
                args = dict(action=PGM_ACTIONS[command], argument=(output - 1))
                reply = await self.core.send_wait(parsers.PerformAction, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

        return accepted
