# -*- coding: utf-8 -*-

import inspect
import logging
import sys
import time
from typing import Optional

from .parsers import Construct, CloseConnection, ErrorMessage, InitializeCommunication, InitializeCommunicationResponse, \
    SetTimeDate, SetTimeDateResponse, PerformAction, PerformActionResponse, ReadStatusResponse, ReadEEPROM, \
    ReadEEPROMResponse, LiveEvent, RAMDataParserMap, Container
from ..panel import Panel as PanelBase

from .event import event_map
from paradox.paradox import PublishPropertyChange

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

PARTITION_ACTIONS = dict(arm=0x04, disarm=0x05, arm_stay=0x01, arm_sleep=0x03,  arm_stay_stayd=0x06, arm_sleep_stay=0x07, disarm_all=0x08)
ZONE_ACTIONS = dict(bypass=0x10, clear_bypass=0x10)
PGM_ACTIONS = dict(on_override=0x30, off_override=0x31, on=0x32, off=0x33, pulse=0)


class Panel(PanelBase):

    event_map = event_map

    mem_map = {
        "status_base1": 0x8000,
        "status_base2": 0x1fe0,
        "elements": {
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

    def get_message(self, name) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
            if name in clsmembers:
                return clsmembers[name]
        except ResourceWarning:
            pass

        return super(Panel, self).get_message(name)

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        super(Panel, self).update_labels()

        logger.debug("Labels updated")

    def parse_message(self, message, direction='topanel') -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel, self).parse_message(message, direction)
            if parent_parsed:
                return parent_parsed

            if direction == 'topanel':
                if message[0] == 0x70 and message[-5] != 0:
                    return CloseConnection.parse(message)
                elif message[0] == 0x00:
                    return InitializeCommunication.parse(message)
                elif message[0] == 0x30:
                    return SetTimeDate.parse(message)
                elif message[0] == 0x40:
                    return PerformAction.parse(message)
                elif message[0] == 0x50 and message[2] < 0x80:
                    return ReadEEPROM.parse(message)
            
            else:
                if message[0] == 0x10:
                    return InitializeCommunicationResponse.parse(message)
                elif message[0] >> 4 == 0x7 and message[-5] == 0:
                    return ErrorMessage.parse(message)
                elif message[0] >> 4 == 0x03:
                    return SetTimeDateResponse.parse(message)
                elif message[0] >> 4 == 0x04:
                    return PerformActionResponse.parse(message)
                elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                    return ReadStatusResponse.parse(message)
                elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                    return ReadEEPROMResponse.parse(message)

            #        elif message[0] == 0x60 and message[2] < 0x80:
            #            return WriteEEPROM.parse(message)
            #        elif message[0] >> 4 == 0x06 and message[2] < 0x80:
            #            return WriteEEPROMResponse.parse(message)
                elif message[0] >> 4 == 0x0e:
                    return LiveEvent.parse(message)

        except Exception:
            logger.exception("Parsing message: %s" % (" ".join("{:02x} ".format(c) for c in message)))

        return None

    def initialize_communication(self, reply, PASSWORD):
        password = self.encode_password(PASSWORD)

        args = dict(product_id=reply.fields.value.product_id,
                    firmware=reply.fields.value.firmware,
                    panel_id=reply.fields.value.panel_id,
                    pc_password=password,
                    user_code=0x000000,
                    _not_used1=0x19,
                    source_id=0x02
                    )

        logger.info("Initializing communication")
        reply = self.core.send_wait(self.get_message('InitializeCommunication'), args=args)

        if reply is None:
            logger.error("Initialization Failed")
            return False

        if reply.fields.value.po.command == 0x10:
            logger.info("Authentication Success")
            return True
        elif reply.fields.value.po.command == 0x70 or reply.fields.value.po.command == 0x00:
            logger.error("Authentication Failed. Wrong Password?")
            return False

    def request_status(self, i):
        args = dict(address=self.mem_map['status_base1'] + i)
        reply = self.core.send_wait(ReadEEPROM, args, reply_expected=0x05)

        return reply

    def handle_status(self, message):
        """Handle MessageStatus"""
        mvars = message.fields.value

        if mvars.address not in RAMDataParserMap:
            logger.warn("Unknown memory address {}".format(mvars.address))
            return

        parser = RAMDataParserMap[mvars.address]
        try:
            properties = parser.parse(mvars.data)
        except Exception:
            logger.exception("Unable to parse RAM Status Block")
            return

        if mvars.address == 0:
            if time.time() - self.core.last_power_update >= cfg.POWER_UPDATE_INTERVAL:
                force = PublishPropertyChange.YES if cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE else PublishPropertyChange.NO

                self.core.last_power_update = time.time()
                self.core.update_properties('system', 'power', dict(vdc=round(properties.vdc, 2)),
                                            publish=force)
                self.core.update_properties('system', 'power', dict(battery=round(properties.battery, 2)),
                                            publish=force)
                self.core.update_properties('system', 'power', dict(dc=round(properties.dc, 2)),
                                            publish=force)
                self.core.update_properties('system', 'rf',
                                            dict(rf_noise_floor=round(properties.rf_noise_floor, 2)),
                                            publish=force)

            for k in properties.troubles:
                if k.startswith('_'):
                    continue

                self.core.update_properties('system', 'troubles', {k: properties.troubles[k]})

            self.process_properties_bulk(properties, mvars.address)

        elif 1 <= mvars.address <= 5:
            self.process_properties_bulk(properties, mvars.address)

    def control_zones(self, zones, command) -> bool:
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
            reply = self.core.send_wait(PerformAction, args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        return accepted

    def control_partitions(self, partitions, command) -> bool:
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
            reply = self.core.send_wait(PerformAction, args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        return accepted

    def control_outputs(self, outputs, command) -> bool:
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
                reply = self.core.send_wait(PerformAction, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

                time.sleep(1)
                args = dict(action=PGM_ACTIONS['off'], argument=(output - 1))
                reply = self.core.send_wait(PerformAction, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True
            else:
                args = dict(action=PGM_ACTIONS[command], argument=(output - 1))
                reply = self.core.send_wait(PerformAction, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

        return accepted
