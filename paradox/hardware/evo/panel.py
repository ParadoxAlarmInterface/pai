# -*- coding: utf-8 -*-

import inspect
import sys
import logging
import binascii
import time
import itertools

from .parsers import *
from ..panel import Panel as PanelBase, iterate_properties

from config import user as cfg

logger = logging.getLogger('PAI').getChild(__name__)

class Panel_EVOBase(PanelBase):
    def get_message(self, name):
        try:
            return super(Panel_EVOBase, self).get_message(name)
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
        except Exception:
            logger.exception("Parsing message: %s" % (" ".join("{:02x} ".format(c) for c in message)))

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

        if vars.address == 1:
            for k in properties.troubles:
                if "not_used" in k:
                    continue

                self.core.update_properties('system', 'trouble', {k: properties.troubles[k]})

        self.process_properties_bulk(properties, vars.address)

    def process_properties_bulk(self, properties, address):
        for key, value in iterate_properties(properties):
            if not isinstance(value, (list, dict)):
                continue

            element_type = key.split('_')[0]

            limit_list = cfg.LIMITS.get(element_type)

            if key in self.core.status_cache and self.core.status_cache[address][key] == value:
                continue

            if address not in self.core.status_cache:
                self.core.status_cache[address] = {}
            self.core.status_cache[address][key] = value

            prop_name = '_'.join(key.split('_')[1:])
            if not prop_name:
                continue

            for i, status in iterate_properties(value):
                if limit_list is None or i in limit_list:
                    if prop_name == 'status':
                        self.core.update_properties(element_type, i, status)
                    else:
                        self.core.update_properties(element_type, i, {prop_name: status})

    def process_event(self, event):
        major = event['major'][0]
        minor = event['minor'][0]
        minor2 = event['minor2'][0]
        partition = event['partition']

        change = None

        # ZONES
        if major in (0, 1):
            change = dict(open=(major == 1))
        elif major in (2, 33, 34):
            change = dict(tamper=(major in (2, 33)))
        elif major == 23:
            change = dict(bypass=not self.core.data['zone'][minor])
        elif major in (24, 26):
            change = dict(alarm=(major == 24))
        elif major in (25, 27):
            change = dict(fire_alarm=(major == 37))
        elif major == 32:
            change = dict(shutdown=True)
        elif major in (42, 44):
            change = dict(supervision_trouble=(major == 42))

        # PARTITIONS
        elif major in (9, 10, 11, 12):  # Arming
            change = dict(arm=True)
        elif major in (13, 14, 15, 16, 17, 18, 22):  # Disarming
            change = dict(arm=False)

        new_event = {'major': event['major'], 'minor': event['minor'], 'type': event['type']}

        if change is not None:
            if event['type'] == 'Zone' and len(self.core.data['zone']) > 0 and minor < len(self.core.data['zone']):
                self.core.update_properties('zone', minor, change)
                new_event['minor'] = (minor, self.core.data['zone'][minor]['label'])
            elif event['type'] == 'User' and len(self.core.data['user']) > 0 and minor < len(self.core.data['user']):
                self.core.update_properties('user', minor, change)
                new_event['minor'] = (minor, self.core.data['user'][minor]['label'])
            # elif event['type'] == 'Partition' and len(self.core.data['partition']) > 0:
            #     pass
            # elif event['type'] == 'Output' and len(self.core.data['output']) and minor < len(self.core.data['output']):
            #     self.core.update_properties('output', minor, change)
            #     new_event['minor'] = (minor, self.core.data['output'][minor]['label'])

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