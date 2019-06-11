# -*- coding: utf-8 -*-

import binascii
import inspect
import logging
import sys
from typing import Optional

from construct import Construct, Container, MappingError, ChecksumError

from .event import event_map
from .parsers import CloseConnection, ErrorMessage, InitializeCommunication, LoginConfirmationResponse, SetTimeDate, \
    SetTimeDateResponse, PerformPartitionAction, PerformActionResponse, ReadEEPROMResponse, LiveEvent, ReadEEPROM, \
    RAMDataParserMap, RequestedEvent
from ..panel import Panel as PanelBase

logger = logging.getLogger('PAI').getChild(__name__)


class Panel_EVOBase(PanelBase):

    event_map = event_map
    property_map = {}

    def get_message(self, name) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
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
                    self.get_message('ReadEEPROM'), args, reply_expected=lambda m: m.fields.value.po.command == 0x05 and m.fields.value.address == address)

                if reply is None:
                    logger.error("Could not read %s: address %d" % (mem_type, address))
                    return

                data = reply.fields.value.data

                fh.write(data)

    def parse_message(self, message, direction='topanel') -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel_EVOBase, self).parse_message(message, direction)
            if parent_parsed:
                return parent_parsed

            if direction == 'topanel':
                if message[0] == 0x70:
                    return CloseConnection.parse(message)
                elif message[0] == 0x00:
                    return InitializeCommunication.parse(message)
                elif message[0] == 0x30:
                    return SetTimeDate.parse(message)
                elif message[0] == 0x40:
                    return PerformPartitionAction.parse(message)
            else:
                if message[0] >> 4 == 0x7:
                    return ErrorMessage.parse(message)
                elif message[0] >> 4 == 0x1:
                    return LoginConfirmationResponse.parse(message)
                elif message[0] >> 4 == 0x03:
                    return SetTimeDateResponse.parse(message)
                elif message[0] >> 4 == 4:
                    return PerformActionResponse.parse(message)
                # elif message[0] == 0x50 and message[2] == 0x80:
                #     return PanelStatus.parse(message)
                # elif message[0] == 0x50 and message[2] < 0x80:
                #     return ReadEEPROM.parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                #     return PanelStatusResponse[message[3]].parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                elif message[0] >> 4 == 0x05:
                    return ReadEEPROMResponse.parse(message)
                # elif message[0] == 0x60 and message[2] < 0x80:
                #     return WriteEEPROM.parse(message)
                # elif message[0] >> 4 == 0x06 and message[2] < 0x80:
                #     return WriteEEPROMResponse.parse(message)
                elif message[0] >> 4 == 0x0e:
                    if message[1] == 0xff:
                        return LiveEvent.parse(message)
                    else:
                        return RequestedEvent.parse(message)

        except ChecksumError as e:
            logger.error("ChecksumError %s, message: %s" % (str(e), binascii.hexlify(message)))
        except Exception:
            logger.exception("Exception parsing message: %s" % (binascii.hexlify(message)))

        return None

    async def initialize_communication(self, reply, PASSWORD) -> bool:
        password = self.encode_password(PASSWORD)

        raw_data = reply.fields.data + reply.checksum
        parsed = InitializeCommunication.parse(raw_data)
        parsed.fields.value.pc_password = password
        payload = InitializeCommunication.build(
            dict(fields=dict(value=parsed.fields.value)))

        logger.info("Initializing communication")
        reply = await self.core.send_wait(message=payload, reply_expected=[0x1, 0x0])

        if reply is None:
            logger.error("Initialization Failed")
            return False

        if reply.fields.value.po.command == 0x0:
            logger.error("Authentication Failed. Wrong Password or User Type is not FullMaster?")
            return False
        else:  # command == 0x1
            if reply.fields.value.po.status.Winload_connected:
                logger.info("Authentication Success")
                return True
            else:
                logger.error("Authentication Failed")
                return False

    def _request_status_reply_check(self, message, address):
        mvars = message.fields.value

        assert mvars.po.command == 0x5
        assert mvars.control.ram_access is True
        assert mvars.control.eeprom_address_bits == 0x0
        assert mvars.bus_address == 0x00  # panel
        assert mvars.address == address

        return True

    async def request_status(self, i) -> Optional[Container]:
        args = dict(address=i, length=64, control=dict(ram_access=True))
        reply = await self.core.send_wait(ReadEEPROM, args, reply_expected=lambda m: self._request_status_reply_check(m, i))

        return reply

    def handle_status(self, message):
        """Handle MessageStatus"""

        mvars = message.fields.value
        # Check message

        if mvars.address not in RAMDataParserMap:
            logger.error(
                "Parser for memory address ({}) is not implemented. Please review your STATUS_REQUESTS setting. Skipping.".format(mvars.address))
            return
        assert len(mvars.data) == 64

        parser = RAMDataParserMap[mvars.address]

        properties = parser.parse(mvars.data)

        if mvars.address == 1:
            for k in properties.troubles:
                if k.startswith("_"):  # ignore private properties
                    continue

                self.core.update_properties('system', 'troubles',
                                            {k: properties.troubles[k]})

        self.process_properties_bulk(properties, mvars.address)

    async def control_partitions(self, partitions, command) -> bool:
        """
        Control Partitions
        :param list partitions: a list of partitions
        :param str command: textual command
        :return: True if we have at least one success
        """
        args = dict(commands=dict((i, command) for i in partitions))

        try:
            reply = await self.core.send_wait(
                PerformPartitionAction, args, reply_expected=0x04)
        except MappingError:
            logger.error('Partition command: "%s" is not supported' % command)
            return False

        return reply is not None
