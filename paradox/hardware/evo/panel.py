# -*- coding: utf-8 -*-

import binascii
import inspect
import logging
import sys
from typing import Optional

from construct import Construct, Container, MappingError

from .parsers import CloseConnection, ErrorMessage, InitializeCommunication, LoginConfirmationResponse, SetTimeDate, \
    SetTimeDateResponse, PerformPartitionAction, PerformActionResponse, ReadEEPROMResponse, LiveEvent, ReadEEPROM, \
    RAMDataParserMap
from ..panel import Panel as PanelBase

from .event import event_map

logger = logging.getLogger('PAI').getChild(__name__)


class Panel_EVOBase(PanelBase):

    event_map = event_map

    def get_message(self, name, direction) -> Construct:
        try:
            return super(Panel_EVOBase, self).get_message(name, direction)
        except ResourceWarning as e:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
            if name in clsmembers:
                return clsmembers[name]
            else:
                raise e

    def dump_memory_to_file(self, file, range_, ram=False):
        mem_type = "RAM" if ram else "EEPROM"
        logger.info("Dump " + mem_type)

        packet_length = 64  # 64 is max
        with open(file, 'wb') as fh:
            for address in range_:
                args = dict(
                    address=address,
                    length=packet_length,
                    control=dict(ram_access=ram))
                reply = self.core.send_wait(
                    self.get_message('ReadEEPROM'), args, reply_expected=0x05)

                retry_count = 3
                for retry in range(1, retry_count + 1):
                    # Avoid errors due to collision with events. It should not come here as we use reply_expected=0x05
                    if reply is None:
                        logger.error("Could not fully read " + mem_type)
                        return

                    if reply.fields.value.address != address:
                        logger.debug(
                            "Fetched and receive %s addresses (received: %d, requested: %d) do not match. Retrying %d of %d"
                            % (mem_type, reply.fields.value.address, address,
                               retry, retry_count))
                        reply = self.core.send_wait(
                            None, None, reply_expected=0x05)
                        continue

                    if retry == retry_count:
                        logger.error('Failed to fetch %s at address: %d' %
                                     (mem_type, address))

                    break

                data = reply.fields.value.data

                fh.write(data)

    def parse_message(self, message) -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel_EVOBase, self).parse_message(message)
            if parent_parsed:
                return parent_parsed
            elif message[0] == 0x70:
                return CloseConnection.parse(message)
            elif message[0] >> 4 == 0x7:
                return ErrorMessage.parse(message)
            elif message[0] == 0x00:
                return InitializeCommunication.parse(message)
            elif message[0] >> 4 == 0x1:
                return LoginConfirmationResponse.parse(message)
            elif message[0] == 0x30:
                return SetTimeDate.parse(message)
            elif message[0] >> 4 == 0x03:
                return SetTimeDateResponse.parse(message)
            elif message[0] == 0x40:
                return PerformPartitionAction.parse(message)
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
                return LiveEvent.parse(message)
        except Exception:
            logger.exception("Parsing message: %s" % (" ".join(
                "{:02x} ".format(c) for c in message)))

        return None

    def initialize_communication(self, reply, PASSWORD) -> bool:
        password = self.encode_password(PASSWORD)

        raw_data = reply.fields.data + reply.checksum
        parsed = InitializeCommunication.parse(raw_data)
        parsed.fields.value.pc_password = password
        payload = InitializeCommunication.build(
            dict(fields=dict(value=parsed.fields.value)))

        logger.info("Initializing communication")
        reply = self.core.send_wait(message=payload, reply_expected=0x1)

        if reply is None:
            logger.error("Initialization Failed")
            return False

        if reply.fields.value.po.status.Windload_connected:
            logger.info("Authentication Success")
            return True
        else:
            logger.error("Authentication Failed. Wrong Password?")
            return False

    def request_status(self, i) -> Optional[Container]:
        args = dict(address=i, length=64, control=dict(ram_access=True))
        reply = self.core.send_wait(ReadEEPROM, args, reply_expected=0x05)

        return reply

    def handle_status(self, message):
        """Handle MessageStatus"""

        vars = message.fields.value
        # Check message

        assert vars.po.command == 0x5
        assert vars.control.ram_access == True
        assert vars.control.eeprom_address_bits == 0x0
        assert vars.bus_address == 0x00  # panel

        if vars.address not in RAMDataParserMap:
            logger.error(
                "Parser for memory address (%d) is not implemented. Please review your STATUS_REQUESTS setting. Skipping."
                % vars.address)
            return
        assert len(vars.data) == 64

        parser = RAMDataParserMap[vars.address]

        properties = parser.parse(vars.data)

        if vars.address == 1:
            for k in properties.troubles:
                if k.startswith("_"):  # ignore private properties
                    continue

                self.core.update_properties('system', 'trouble',
                                            {k: properties.troubles[k]})

        self.process_properties_bulk(properties, vars.address)

    def control_partitions(self, partitions, command) -> bool:
        """
        Control Partitions
        :param list partitions: a list of partitions
        :param str command: textual command
        :return: True if we have at least one success
        """
        args = dict(commands=dict((i, command) for i in partitions))

        try:
            reply = self.core.send_wait(
                PerformPartitionAction, args, reply_expected=0x04)
        except MappingError:
            logger.error('Partition command: "%s" is not supported' % command)
            return False

        return reply is not None
