# -*- coding: utf-8 -*-

import inspect
import sys
import logging
import binascii
import time
import itertools

from .parsers import *
from ..panel import Panel as PanelBase

from config import user as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class Panel(PanelBase):
    mem_map = dict(
        elements=dict(
            zone=dict(
                label_offset=0, addresses=[
                    range(0x00430, 0x00730, 0x10),  # EVO48
                    range(0x00730, 0x00a30, 0x10),  # EVO96 = EVO48 + 48 zones
                    range(0x062f7, 0x068f7, 0x10)  # EVO192 = EVO96 + 96 zones
                ]),
            output=dict(
                label_offset=0, addresses=[range(0x07082, 0x7482, 0x20)], template=dict(
                    on=False,
                    pulse=False)
                ),
            partition=dict(
                label_offset=0, addresses=[
                    range(0x03a6b, 0x03c17, 0x6b),  # EVO48
                    range(0x03c17, 0x03dc3, 0x6b)  # EVO96 & EVO192 = EVO48 + 4 partitions
                ]),
            user=dict(
                label_offset=0, addresses=[range(0x03e47, 0x04e47, 0x10)]),
            bus=dict(  # modules
                label_offset=0, addresses=[
                    range(0x04e47, 0x05637, 0x10),  # EVO48
                    range(0x05637, 0x05e27, 0x10)  # EVO96 & EVO192 = EVO48 + 127 modules
                ]),
            door=dict(
                label_offset=0, addresses=[range(0x0345c, 0x365c, 0x10)]),
        )
    )

    def get_message(self, name):
        try:
            return super(Panel, self).get_message(name)
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
            # elif message[0] == 0x60 and message[2] < 0x80:
            #     return WriteEEPROM.parse(message)
            # elif message[0] >> 4 == 0x06 and message[2] < 0x80:
            #     return WriteEEPROMResponse.parse(message)
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

        if reply.fields.value.po.status.Windload_connected:
            logger.info("Authentication Success")
            return True
        else:
            logger.error("Authentication Failed. Wrong Password?")
            return False

    def request_status(self, i):
        args = dict(address=i, length=64, control=dict(ram_access=True))
        reply = self.core.send_wait(ReadEEPROM, args, reply_expected=0x05)

        return reply

    def process_status_bulk(self, message):
        for k in message.fields.value:
            element_type = k.split('_')[0]

            if element_type == 'pgm':
                element_type = 'output'
                limit_list = cfg.OUTPUTS
            elif element_type == 'partition':
                limit_list = cfg.PARTITIONS
            elif element_type == 'zone':
                limit_list = cfg.ZONES
            elif element_type == 'bus':
                limit_list = cfg.BUSES
            else:
                continue

            if k in self.core.status_cache and self.core.status_cache[k] == message.fields.value[k]:
                continue

            self.core.status_cache[k] = message.fields.value[k]

            prop_name = '_'.join(k.split('_')[1:])
            if prop_name == 'status':
                for i in message.fields.value[k]:
                    if i in limit_list:
                        self.core.update_properties(element_type, i, message.fields.value[k][i])
            else:
                for i in message.fields.value[k]:
                    if i in limit_list:
                        status = message.fields.value[k][i]
                        self.core.update_properties(element_type, i, {prop_name: status})

    def handle_status(self, message):
        """Handle MessageStatus"""

        vars = message.fields.value
        # Check message

        assert vars.po.command == 0x5
        assert vars.control.ram_access == True
        assert vars.control.eeprom_address_bits == 0x0
        assert vars.bus_address == 0x00 # panel

        assert vars.address in RAMDataParserMap
        assert len(vars.data) == 64

        parser = RAMDataParserMap[vars.address]

        properties = parser.parse(vars.data)

        # if message.fields.value.address == 1:
        #     if time.time() - self.core.last_power_update >= cfg.POWER_UPDATE_INTERVAL:
        #         self.core.last_power_update = time.time()
        #         self.core.update_properties('system', 'power', dict(vdc=round(message.fields.value.vdc, 2)),
        #                                     force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
        #         self.core.update_properties('system', 'power', dict(battery=round(message.fields.value.battery, 2)),
        #                                     force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
        #         self.core.update_properties('system', 'power', dict(dc=round(message.fields.value.dc, 2)),
        #                                     force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
        #         self.core.update_properties('system', 'rf',
        #                                     dict(rf_noise_floor=round(message.fields.value.rf_noise_floor, 2)),
        #                                     force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
        #
        #     for k in message.fields.value.troubles:
        #         if "not_used" in k:
        #             continue
        #
        #         self.core.update_properties('system', 'trouble', {k: message.fields.value.troubles[k]})
        #
        #     self.process_status_bulk(message)
        #
        # elif message.fields.value.status_request >= 1 and message.fields.value.status_request <= 5:
        #     self.process_status_bulk(message)
