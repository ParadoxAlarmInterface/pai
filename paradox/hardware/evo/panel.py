# -*- coding: utf-8 -*-

import inspect
import sys
import logging
import binascii

from .parsers import *
from ..panel import Panel as PanelBase


MEM_ZONE_48_START = 0x00430
MEM_ZONE_48_END = MEM_ZONE_48_START + 0x10 * 48
MEM_ZONE_96_START = MEM_ZONE_48_END
MEM_ZONE_96_END = MEM_ZONE_48_END + 0x10 * 48
MEM_ZONE_192_START = 0x62F7
MEM_ZONE_192_END = MEM_ZONE_192_START + 0x10 * 96

MEM_OUTPUT_START = 0x07082
MEM_OUTPUT_END = MEM_OUTPUT_START + 0x10 * 32 * 2

MEM_PARTITION_START = 0x03a6b
MEM_PARTITION_48_END = MEM_PARTITION_START + 0x6b * 4
MEM_PARTITION_END = MEM_PARTITION_START + 0x6b * 8

MEM_USER_START = 0x03e47
MEM_USER_END = MEM_USER_START + 0x10 * 256  # EVO192

MEM_MODULE_START = MEM_USER_END
MEM_MODULE_48_END = MEM_MODULE_START + 0x10 * 127
MEM_MODULE_END = MEM_MODULE_START + 0x10 * 254  # EVO192

MEM_DOOR_START = 0x0345c
MEM_DOOR_END = MEM_DOOR_START + 0x10 * 32

logger = logging.getLogger('PAI').getChild(__name__)


class Panel(PanelBase):
    def get_message(self, name):
        try:
            return super(Panel, self).get_message(name)
        except ResourceWarning as e:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
            if name in clsmembers:
                return clsmembers[name]
            else:
                raise e

    def update_labels(self):
        # self.dump_memory_to_file('eeprom.bin', range(0, 0xffff, 64))
        # self.dump_memory_to_file('ram.bin', range(0, 59), True)

        logger.info("Updating Labels from Panel")

        output_template = dict(
            on=False,
            pulse=False)

        # Zones
        eeprom_zone_ranges = [range(MEM_ZONE_48_START, MEM_ZONE_48_END, 0x10)]
        if self.product_id in ['DIGIPLEX_EVO_96', 'DIGIPLEX_EVO_192']:
            eeprom_zone_ranges.append(range(MEM_ZONE_96_START, MEM_ZONE_96_END, 0x10))
        if self.product_id in ['DIGIPLEX_EVO_192']:
            eeprom_zone_ranges.append(range(MEM_ZONE_192_START, MEM_ZONE_192_END, 0x10))

        self.load_labels(self.core.zones, self.core.labels['zone'], eeprom_zone_ranges)
        logger.info("Zones: {}".format(', '.join(self.core.labels['zone'])))

        # Users
        eeprom_user_ranges = [range(MEM_USER_START, MEM_USER_END, 0x10)]
        self.load_labels(self.core.users, self.core.labels['user'], eeprom_user_ranges)
        logger.info("Users: {}".format(', '.join(self.core.labels['user'])))

        # # Modules
        # if self.product_id in ['DIGIPLEX_EVO_48']:
        #     eeprom_module_ranges = [range(MEM_MODULE_START, MEM_MODULE_END, 0x10)]
        # else:
        #     eeprom_module_ranges = [range(MEM_MODULE_START, MEM_MODULE_48_END, 0x10)]
        # self.load_labels(self.core.modules, self.core.labels['module'], eeprom_module_ranges)
        # logger.info("Modules: {}".format(', '.join(self.core.labels['module'])))

        # Output/PGMs
        eeprom_output_ranges = [range(MEM_OUTPUT_START, MEM_OUTPUT_END, 0x20)]
        self.load_labels(self.core.outputs, self.core.labels['output'], eeprom_output_ranges)
        logger.info("Output/PGMs: {}".format(', '.join(self.core.labels['output'])))

        # Partitions
        if self.product_id in ['DIGIPLEX_EVO_48']:
            eeprom_partition_ranges = [range(MEM_PARTITION_START, MEM_PARTITION_48_END, 107)]
        else:
            eeprom_partition_ranges = [range(MEM_PARTITION_START, MEM_PARTITION_END, 107)]

        self.load_labels(self.core.partitions, self.core.labels['partition'], eeprom_partition_ranges)
        logger.info("Partitions: {}".format(', '.join(self.core.labels['partition'])))

        # # Doors
        # eeprom_door_ranges = [range(MEM_DOOR_START, MEM_DOOR_END, 0x10)]
        # self.load_labels(self.core.doors, self.core.labels['door'], eeprom_door_ranges)
        # logger.info("Doors: {}".format(', '.join(self.core.labels['door'])))

        logger.debug("Labels updated")

    def dump_memory_to_file(self, file, range_, ram=False):
        mem_type = "RAM" if ram else "EEPROM"
        logger.info("Dump " + mem_type)

        packet_length = 64  # 64 is max
        with open(file, 'wb') as fh:
            for address in range_:
                args = dict(address=address, length=packet_length, control=dict(ram_access=ram))
                reply = self.core.send_wait(self.get_message('ReadEEPROM'), args, reply_expected=0x05)

                retry_count = 3
                for retry in range(1, retry_count + 1):
                    # Avoid errors due to collision with events. It should not come here as we use reply_expected=0x05
                    if reply is None:
                        logger.error("Could not fully read " + mem_type)
                        return

                    if reply.fields.value.address != address:
                        logger.debug(
                            "Fetched and receive %s addresses (received: %d, requested: %d) do not match. Retrying %d of %d" % (
                                mem_type,
                                reply.fields.value.address, address, retry, retry_count))
                        reply = self.core.send_wait(None, None, reply_expected=0x05)
                        continue

                    if retry == retry_count:
                        logger.error('Failed to fetch %s at address: %d' % (mem_type, address))

                    break

                data = reply.fields.value.data

                fh.write(data)

    def load_labels(self,
                    labelDictIndex,
                    labelDictName,
                    ranges,
                    field_length=16,
                    template=dict(label='')):
        """Load labels from panel"""
        i = 1

        for range_ in ranges:
            for address in range_:
                args = dict(address=address, length=field_length)
                reply = self.core.send_wait(self.get_message('ReadEEPROM'), args, reply_expected=0x05)

                retry_count = 3
                for retry in range(1, retry_count + 1):
                    # Avoid errors due to collision with events. It should not come here as we use reply_expected=0x05
                    if reply is None:
                        logger.error("Could not fully load labels")
                        return

                    if reply.fields.value.address != address:
                        logger.debug(
                            "Fetched and receive label EEPROM addresses (received: %d, requested: %d) do not match. Retrying %d of %d" % (
                                reply.fields.value.address, address, retry, retry_count))
                        reply = self.core.send_wait(None, None, reply_expected=0x05)
                        continue

                    if retry == retry_count:
                        logger.error('Failed to fetch label at address: %d' % address)

                    break

                data = reply.fields.value.data
                label = data.strip(b'\0 ').replace(b'\0', b'_').replace(b' ', b'_').decode('utf-8')

                if label not in labelDictName:
                    properties = template.copy()
                    properties['label'] = label
                    labelDictIndex[i] = properties

                    labelDictName[label] = i
                i += 1

    def parse_message(self, message):
        try:
            if message is None or len(message) == 0:
                return None

            if message[0] == 0x70:
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
                return PerformAction.parse(message)
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
            elif message[0] == 0x60 and message[2] < 0x80:
                return WriteEEPROM.parse(message)
            elif message[0] >> 4 == 0x06 and message[2] < 0x80:
                return WriteEEPROMResponse.parse(message)
            elif message[0] >> 4 == 0x0e:
                return LiveEvent.parse(message)
            else:
                logger.error("Unknown message: %s" % (" ".join("{:02x} ".format(c) for c in message)))
        except Exception:
            logger.exception("Parsing message")

        s = 'PARSE: '
        for c in message:
            s += "{:02x} ".format(c)

        logger.debug(s)

        return None

    def encode_password(self, password):
        return binascii.unhexlify(password)

    def initialize_communication(self, reply, PASSWORD):
        password = self.encode_password(PASSWORD)

        raw_data = reply.fields.data + reply.checksum
        parsed = InitializeCommunication.parse(raw_data)
        parsed.fields.value.pc_password = password
        payload = InitializeCommunication.build(dict(fields=dict(value=parsed.fields.value)))

        logger.info("Initializing communication")
        reply = self.core.send_wait(message=payload, reply_expected=0x1)

        if reply is None:
            return False

        if reply.fields.value.po.status.Windload_connected == True:
            logger.info("Authentication Success")
            return True
        else:
            logger.error("Authentication Failed. Wrong Password?")
            return False