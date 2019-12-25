# -*- coding: utf-8 -*-

import binascii
import inspect
import logging
from typing import Optional

from construct import Construct, Container, MappingError, ChecksumError

from paradox.exceptions import StatusRequestException
from . import parsers
from .event import event_map
from .property import property_map
from ..panel import Panel as PanelBase

logger = logging.getLogger('PAI').getChild(__name__)

ZONE_ACTIONS = dict(
    bypass={
        "flags": {
            "bypassed": True
        },
        "operation": "set",
    },
    clear_bypass={
        "flags": {
            "bypassed": True
        },
        "operation": "clear",
    },
    clear_alarm_memory={
        "flags": {
            "generated_alarm": True
        },
        "operation": "clear",
    }
)


class Panel_EVOBase(PanelBase):
    event_map = event_map
    property_map = property_map
    max_eeprom_response_data_length = 64

    def get_message(self, name: str) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(parsers))
            if name in clsmembers:
                return clsmembers[name]
        except ResourceWarning:
            pass

        return super(Panel_EVOBase, self).get_message(name)

    async def dump_memory(self):
        """
        Dumps EEPROM and RAM memory to files
        :return:
        """
        await self.dump_memory_to_file('eeprom.bin', range(0, 0xffff, 64))
        await self.dump_memory_to_file('ram.bin', range(0, 59), True)

    async def dump_memory_to_file(self, file, range_, ram=False):
        mem_type = "RAM" if ram else "EEPROM"
        logger.info("Dump " + mem_type)

        packet_length = 64  # 64 is max
        with open(file, 'wb') as fh:
            for address in range_:
                args = dict(
                    address=address,
                    length=packet_length,
                    control=dict(ram_access=ram))
                logger.info("Dumping %s: address %d" % (mem_type, address))
                reply = await self.core.send_wait(
                    parsers.ReadEEPROM, args, reply_expected=lambda m: m.fields.value.po.command == 0x05 and m.fields.value.address == address)

                if reply is None:
                    logger.error("Could not read %s: address %d" % (mem_type, address))
                    return

                data = reply.fields.value.data

                fh.write(data)

    def parse_message(self, message: bytes, direction='topanel') -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel_EVOBase, self).parse_message(message, direction)
            if parent_parsed:
                return parent_parsed

            if direction == 'topanel':
                if message[0] == 0x70:
                    return parsers.CloseConnection.parse(message)
                elif message[0] == 0x00:
                    return parsers.InitializeCommunication.parse(message)
                elif message[0] == 0x30:
                    return parsers.SetTimeDate.parse(message)
                elif message[0] == 0x40:
                    return parsers.PerformPartitionAction.parse(message)
                elif message[0] == 0xd0:
                    return parsers.PerformZoneAction.parse(message)
            else:
                if message[0] >> 4 == 0x7:
                    return parsers.ErrorMessage.parse(message)
                elif message[0] >> 4 == 0x1:
                    return parsers.LoginConfirmationResponse.parse(message)
                elif message[0] >> 4 == 0x03:
                    return parsers.SetTimeDateResponse.parse(message)
                elif message[0] >> 4 == 4:
                    return parsers.PerformPartitionActionResponse.parse(message)
                elif message[0] >> 4 == 0xd:
                    return parsers.PerformZoneActionResponse.parse(message)
                # elif message[0] == 0x50 and message[2] == 0x80:
                #     return PanelStatus.parse(message)
                # elif message[0] == 0x50 and message[2] < 0x80:
                #     return ReadEEPROM.parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                #     return PanelStatusResponse[message[3]].parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                elif message[0] >> 4 == 0x05:
                    return parsers.ReadEEPROMResponse.parse(message)
                # elif message[0] == 0x60 and message[2] < 0x80:
                #     return WriteEEPROM.parse(message)
                # elif message[0] >> 4 == 0x06 and message[2] < 0x80:
                #     return WriteEEPROMResponse.parse(message)
                elif message[0] >> 4 == 0x0e:
                    if message[1] == 0xff:
                        return parsers.LiveEvent.parse(message)
                    else:
                        return parsers.RequestedEvent.parse(message)

        except ChecksumError as e:
            logger.error("ChecksumError %s, message: %s" % (str(e), binascii.hexlify(message)))
        except Exception:
            logger.exception("Exception parsing message: %s" % (binascii.hexlify(message)))

        return None

    async def initialize_communication(self, reply: Container, password) -> bool:
        encoded_password = self.encode_password(password)

        raw_data = reply.fields.data + reply.checksum
        parsed = parsers.InitializeCommunication.parse(raw_data)
        parsed.fields.value.pc_password = encoded_password
        payload = parsers.InitializeCommunication.build(
            dict(fields=dict(value=parsed.fields.value)))

        logger.info("Initializing communication")
        reply = await self.core.send_wait(message=payload, reply_expected=[0x1, 0x0])

        if reply is None:
            logger.error("Initialization Failed")
            return False

        if reply.fields.value.po.command == 0x0:
            logger.error("Authentication Failed. Wrong PASSWORD. Make sure you use correct PC Password. In Babyware: "
                         "Right click on your panel -> Properties -> PC Communication (Babyware) -> PC Communication "
                         "(Babyware) Tab.")
            return False
        else:  # command == 0x1
            if reply.fields.value.po.status.Winload_connected:
                logger.info("Authentication Success")
                return True
            else:
                logger.error("Authentication Failed")
                return False

    @staticmethod
    def _request_status_reply_check(message: Container, address: int):
        mvars = message.fields.value

        if (mvars.po.command == 0x5
            and mvars.control.ram_access is True
            and mvars.control.eeprom_address_bits == 0x0
            and mvars.bus_address == 0x00  # panel
            and mvars.address == address
        ):
            return True

        return False

    async def request_status(self, i: int) -> Optional[Container]:
        args = dict(address=i, length=64, control=dict(ram_access=True))
        reply = await self.core.send_wait(parsers.ReadEEPROM, args, reply_expected=lambda m: self._request_status_reply_check(m, args['address']))
        if reply is not None:
            logger.debug("Received status response: %d" % i)
            return self.handle_status(reply, parsers.RAMDataParserMap)
        else:
            raise StatusRequestException("No reply to status request: %d" % i)

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """
        Control Partitions
        :param list partitions: a list of partitions
        :param str command: textual command
        :return: True if we have at least one success
        """
        args = dict(commands=dict((i, command) for i in partitions))

        try:
            reply = await self.core.send_wait(
                parsers.PerformPartitionAction, args, reply_expected=0x04)
        except MappingError:
            logger.error('Partition command: "%s" is not supported' % command)
            return False

        return reply is not None

    async def control_zones(self, zones: list, command: str) -> bool:
        """
        Control zones
        :param list zones: a list of zones
        :param str command: textual command
        :return: True if we have at least one success
        """
        if command not in ZONE_ACTIONS:
            return False

        args = ZONE_ACTIONS[command].copy()
        args["zones"] = zones

        try:
            reply = await self.core.send_wait(
                parsers.PerformZoneAction, args, reply_expected=0xd)
        except MappingError:
            logger.error('Zone command: "%s" is not supported' % command)
            return False

        return reply is not None