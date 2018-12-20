# -*- coding: utf-8 -*-

import inspect
import logging
import sys
import time
from typing import Optional

from config import user as cfg
from .parsers import Construct, CloseConnection, ErrorMessage, InitializeCommunication, InitializeCommunicationResponse, \
    SetTimeDate, SetTimeDateResponse, PerformAction, PerformActionResponse, ReadStatusResponse, ReadEEPROM, \
    ReadEEPROMResponse, LiveEvent, RAMDataParserMap, Container
from ..panel import Panel as PanelBase

logger = logging.getLogger('PAI').getChild(__name__)

PARTITION_ACTIONS = dict(arm=0x04, disarm=0x05, arm_stay=0x01, arm_sleep=0x03,  arm_stay_stayd=0x06, arm_sleep_stay=0x07, disarm_all=0x08)
ZONE_ACTIONS = dict(bypass=0x10, clear_bypass=0x10)
PGM_ACTIONS = dict(on_override=0x30, off_override=0x31, on=0x32, off=0x33, pulse=0)


class Panel(PanelBase):

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
            return super(Panel, self).get_message(name)
        except ResourceWarning as e:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
            if name in clsmembers:
                return clsmembers[name]
            else:
                raise e

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        super(Panel, self).update_labels()

        logger.debug("Labels updated")

    def parse_message(self, message) -> Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super(Panel, self).parse_message(message)
            if parent_parsed:
                return parent_parsed
            elif message[0] == 0x70:
                return CloseConnection.parse(message)
            elif message[0] >> 4 == 0x7:
                return ErrorMessage.parse(message)
            elif message[0] == 0x00:
                return InitializeCommunication.parse(message)
            elif message[0] == 0x10:
                return InitializeCommunicationResponse.parse(message)
            elif message[0] == 0x30:
                return SetTimeDate.parse(message)
            elif message[0] >> 4 == 0x03:
                return SetTimeDateResponse.parse(message)
            elif message[0] == 0x40:
                return PerformAction.parse(message)
            elif message[0] >> 4 == 0x04:
                return PerformActionResponse.parse(message)
            elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                return ReadStatusResponse.parse(message)
            elif message[0] == 0x50 and message[2] < 0x80:
                return ReadEEPROM.parse(message)
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
                    not_used1=0x19,
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
        elif reply.fields.value.po.command == 0x07 or reply.fields.value.po.command == 0x00:
            logger.error("Authentication Failed. Wrong Password?")
            return False

    def request_status(self, i):
        args = dict(address=self.mem_map['status_base1'] + i)
        reply = self.core.send_wait(ReadEEPROM, args, reply_expected=0x05)

        return reply

    def handle_status(self, message):
        """Handle MessageStatus"""
        vars = message.fields.value

        if vars.address not in RAMDataParserMap:
            logger.warn("Unknown memory address {}".format(vars.address))
            return

        parser = RAMDataParserMap[vars.address]
        try:
            properties = parser.parse(vars.data)
        except Exception:
            logger.exception("Unable to parse RAM Status Block")
            return

        if vars.address == 0:
            if time.time() - self.core.last_power_update >= cfg.POWER_UPDATE_INTERVAL:
                self.core.last_power_update = time.time()
                self.core.update_properties('system', 'power', dict(vdc=round(properties.vdc, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'power', dict(battery=round(properties.battery, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'power', dict(dc=round(properties.dc, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'rf',
                                            dict(rf_noise_floor=round(properties.rf_noise_floor, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)

            for k in properties.troubles:
                if "not_used" in k:
                    continue

                self.core.update_properties('system', 'trouble', {k: properties.troubles[k]})

            self.process_properties_bulk(properties, vars.address)

        elif vars.address >= 1 and vars.address <= 5:
            self.process_properties_bulk(properties, vars.address)

    def process_event(self, event):
        major = event['major'][0]
        minor = event['minor'][0]

        change = None

        # ZONES
        if major in (0, 1):
            change = dict(open=(major == 1))
        elif major == 35:
            change = dict(bypass=not self.core.data['zone'][minor])
        elif major in (36, 38):
            change = dict(alarm=(major == 36))
        elif major in (37, 39):
            change = dict(fire_alarm=(major == 37))
        elif major == 41:
            change = dict(shutdown=True)
        elif major in (42, 43):
            change = dict(tamper=(major == 42))
        elif major in (49, 50):
            change = dict(low_battery=(major == 49))
        elif major in (51, 52):
            change = dict(supervision_trouble=(major == 51))

        # PARTITIONS
        elif major == 2:
            if minor in (2, 3, 4, 5, 6):
                change = dict(alarm=True)
            elif minor == 7:
                change = dict(alarm=False)
            elif minor == 11:
                change = dict(arm=False, arm_full=False, arm_sleep=False, arm_stay=False, alarm=False)
            elif minor == 12:
                change = dict(arm=True)
            elif minor == 14:
                change = dict(exit_delay=True)
        elif major == 3:
            if minor in (0, 1):
                change = dict(bell=(minor == 1))
        elif major == 6:
            if minor == 3:
                change = dict(arm=True, arm_full=False, arm_sleep=False, arm_stay=True, alarm=False)
            elif minor == 4:
                change = dict(arm=True, arm_full=False, arm_sleep=True, arm_stay=False, alarm=False)
        # Wireless module
        elif major in (53, 54):
            change = dict(supervision_trouble=(major == 53))
        elif major in (53, 56):
            change = dict(tamper_trouble=(major == 55))

        new_event = {'major': event['major'], 'minor': event['minor'], 'type': event['type']}

        if change is not None:
            if event['type'] == 'Zone' and len(self.core.data['zone']) > 0 and minor < len(self.core.data['zone']):
                self.core.update_properties('zone', minor, change)
                new_event['minor'] = (minor, self.core.data['zone'][minor]['label'])
            elif event['type'] == 'Partition' and len(self.core.data['partition']) > 0:
                pass
            elif event['type'] == 'Output' and len(self.core.data['output']) and minor < len(self.core.data['output']):
                self.core.update_properties('output', minor, change)
                new_event['minor'] = (minor, self.core.data['output'][minor]['label'])

        return new_event

    def generate_event_notifications(self, event):
        major_code = event['major'][0]
        minor_code = event['minor'][0]

        # IGNORED

        # Clock loss
        if major_code == 45 and minor_code == 6:
            return

        # Open Close
        if major_code in [0, 1]:
            return

        # Squawk on off, Partition Arm Disarm
        if major_code == 2 and minor_code in [8, 9, 11, 12, 14]:
            return

        # Bell Squawk
        if major_code == 3 and minor_code in [2, 3]:
            return

        # Arm in Sleep
        if major_code == 6 and minor_code in [3, 4]:
            return

        # Arming Through Winload
        # Partial Arming
        if major_code == 30 and minor_code in [3, 5]:
            return

        # Disarming Through Winload
        if major_code == 34 and minor_code == 1:
            return

        # Software cfg.Log on
        if major_code == 48 and minor_code == 2:
            return

        # CRITICAL Events

        # Fire Delay Started
        # Zone in Alarm
        # Fire Alarm
        # Zone Alarm Restore
        # Fire Alarm Restore
        # Zone Tampered
        # Zone Tamper Restore
        # Non Medical Alarm
        if major_code in [24, 36, 37, 38, 39, 40, 42, 43, 57] or \
            (major_code in [44, 45] and minor_code in [1, 2, 3, 4, 5, 6, 7]):

            detail = event['minor'][1]
            self.core.interface.notify("Paradox", "{} {}".format(event['major'][1], detail), logging.CRITICAL)

        # Silent Alarm
        # Buzzer Alarm
        # Steady Alarm
        # Pulse Alarm
        # Strobe
        # Alarm Stopped
        # Entry Delay
        elif major_code == 2:
            if minor_code in [2, 3, 4, 5, 6, 7, 13]:
                self.core.interface.notify("Paradox", event['minor'][1], logging.CRITICAL)

            elif minor_code == 13:
                self.core.interface.notify("Paradox", event['minor'][1], logging.INFO)

        # Special Alarm, New Trouble and Trouble Restore
        elif major_code in [40, 44, 45] and minor_code in [1, 2, 3, 4, 5, 6, 7]:
            self.core.interface.notify("Paradox", "{}: {}".format(event['major'][1], event['minor'][1]), logging.CRITICAL)
        # Signal Weak
        elif major_code in [18, 19, 20, 21]:
            if event['minor'][0] >= 0 and event['minor'][0] < len(self.core.data['zone']):
                label = self.core.data['zone'][event['minor'][0]]['label']
            else:
                label = event['minor'][1]

            self.core.interface.notify("Paradox", "{}: {}".format(event['major'][1], label), logging.INFO)
        else:
            # Remaining events trigger lower level notifications
            self.core.interface.notify("Paradox", "{}: {}".format(event['major'][1], event['minor'][1]), logging.INFO)

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
