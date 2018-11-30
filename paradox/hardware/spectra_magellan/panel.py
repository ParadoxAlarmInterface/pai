# -*- coding: utf-8 -*-

import inspect
import sys
import logging
import time
from .parsers import *
from ..panel import Panel as PanelBase
from config import user as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class Panel(PanelBase):

    mem_map = dict(
        status_base1=0x8000,
        status_base2=0x1fe0,
        elements=dict(
            zone=dict(
                label_offset=0, addresses=[range(0x010, 0x210, 0x10)]),
            output=dict(
                label_offset=0, addresses=[range(0x210, 0x270, 0x10)], template=dict(
                    on=False,
                    pulse=False)
                ),
            partition=dict(
                label_offset=0, addresses=[range(0x270, 0x290, 0x10)]),
            user=dict(
                label_offset=0, addresses=[range(0x290, 0x490, 0x10)]),
            bus=dict(
                label_offset=0, addresses=[range(0x490, 0x580, 0x10)]),
            repeater=dict(
                label_offset=0, addresses=[range(0x580, 0x5a0, 0x10)]),
            keypad=dict(
                label_offset=0, addresses=[range(0x5a0, 0x620, 0x10)]),
            site=dict(
                label_offset=0, addresses=[range(0x620, 0x630, 0x10)]),
            siren=dict(label_offset=0, addresses=[range(0x630, 0x670, 0x10)])
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

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        super(Panel, self).update_labels()

        logger.debug("Labels updated")

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
            elif message[0] == 0x10:
                return InitializeCommunicationResponse.parse(message)
            elif message[0] == 0x30:
                return SetTimeDate.parse(message)
            elif message[0] >> 4 == 0x03:
                return SetTimeDateResponse.parse(message)
            elif message[0] == 0x40:
                return PerformAction.parse(message)
            elif message[0] >> 4 == 4:
                return PerformActionResponse.parse(message)
            elif message[0] == 0x50 and message[2] == 0x80:
                return PanelStatus.parse(message)
            elif message[0] == 0x50 and message[2] < 0x80:
                return ReadEEPROM.parse(message)
            elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                return PanelStatusResponse[message[3]].parse(message)
            elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                return ReadEEPROMResponse.parse(message)
            #        elif message[0] == 0x60 and message[2] < 0x80:
            #            return WriteEEPROM.parse(message)
            #        elif message[0] >> 4 == 0x06 and message[2] < 0x80:
            #            return WriteEEPROMResponse.parse(message)
            elif message[0] >> 4 == 0x0e:
                return LiveEvent.parse(message)
            else:
                logger.warn("Unknown message")
        except Exception:
            logger.exception("Parsing message")

        s = 'PARSE: '
        for c in message:
            s += "{:02x} ".format(c)

        logger.debug(s)

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
            elif element_type == 'wireless-repeater':
                element_type = 'repeater'
                limit_list == cfg.REPEATERS
            elif element_type == 'wireless-keypad':
                element_type = 'keypad'
                limit_list == cfg.KEYPADS
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

        if message.fields.value.status_request == 0:
            if time.time() - self.core.last_power_update >= cfg.POWER_UPDATE_INTERVAL:
                self.core.last_power_update = time.time()
                self.core.update_properties('system', 'power', dict(vdc=round(message.fields.value.vdc, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'power', dict(battery=round(message.fields.value.battery, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'power', dict(dc=round(message.fields.value.dc, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)
                self.core.update_properties('system', 'rf',
                                            dict(rf_noise_floor=round(message.fields.value.rf_noise_floor, 2)),
                                            force_publish=cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE)

            for k in message.fields.value.troubles:
                if "not_used" in k:
                    continue

                self.core.update_properties('system', 'trouble', {k: message.fields.value.troubles[k]})

            self.process_status_bulk(message)

        elif message.fields.value.status_request >= 1 and message.fields.value.status_request <= 5:
            self.process_status_bulk(message)

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