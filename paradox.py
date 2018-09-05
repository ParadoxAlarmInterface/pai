# -*- coding: utf-8 -*-

import paradox_messages_sp as msg
from serial_connection import *
import logging
import sys
import time
import json
from threading import Lock

from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)

MEM_STATUS_BASE1 = 0x8000
MEM_STATUS_BASE2 = 0x1fe0
MEM_ZONE_START = 0x010
MEM_ZONE_END = MEM_ZONE_START + 0x10 * 16 # For 16 Zones
MEM_OUTPUT_START = 0x210
MEM_OUTPUT_END = MEM_OUTPUT_START + 0x10 * 16 # For 16 Outputs
MEM_PARTITION_START = 0x310
MEM_PARTITION_END = 0x310
MEM_STEP = 0x20

serial_lock = Lock()

class Paradox:
    def __init__(self,
                 connection,
                 interface,
                 retries=3):

        self.connection = connection
        self.connection.timeout(0.5)
        self.retries = retries
        self.interface = interface

        # Keep track of alarm state
        self.labels = {'zone': {}, 'partition': {}, 'output': {}}
        self.zones = dict()
        self.partitions = dict()
        self.outputs = dict()
        self.power = dict()
        self.last_power_update = 0
        self.run = False

    def connect(self):
        logger.info("Connecting to panel")
        
        # Reset all states
        self.labels = {'zone': {}, 'partition': {}, 'output': {}}
        self.zones = dict()
        self.partitions = dict()
        self.outputs = dict()
        self.power = dict()
        self.last_power_update = 0

        self.run = True
        
        try:
            reply = self.send_wait_for_reply(msg.InitiateCommunication, None, reply_expected=0x07)

            if reply is None:
                self.run = False
                return False

            logger.info("Interface connected")
            logger.info("Found Panel {} version {}.{} build {}".format(
                (reply.fields.value.label.decode('latin').strip()),
                reply.fields.value.application.version,
                reply.fields.value.application.revision,
                reply.fields.value.application.build))
            reply = self.send_wait_for_reply(msg.StartCommunication, None, reply_expected=0x00)
            
            if reply is None:
                self.run = False
                return False
            
            args = dict(product_id=reply.fields.value.product_id,
                        firmware=reply.fields.value.firmware, 
                        panel_id=reply.fields.value.panel_id,
                        pc_password=0x0000,
                        ) 

            reply = self.send_wait_for_reply(msg.InitializeCommunication, args=args, reply_expected=0x10)
            
            if reply is None:
                self.run = False
                return False
            
            self.update_labels()
            
            logger.info("Connection OK")

            return True
        except:
            logger.exception("Connect error")

        self.run = False
        return False

    def loop(self):
        logger.debug("Loop start")
        args = {}
        
        while self.run:
            #logger.debug("Getting alarm status")
            
            tstart = time.time()
            try:
                for i in STATUS_REQUESTS:
                    args = dict(address=MEM_STATUS_BASE1 + i)
                    reply = self.send_wait_for_reply(msg.ReadEEPROM, args, reply_expected=0x05)
                    if reply is not None:
                        self.handle_status(reply)
            except:
                logger.exception("Loop")
            
            # Listen for events
            while (time.time() - tstart) < KEEP_ALIVE_INTERVAL: 
                self.send_wait_for_reply(None, timeout=1)

    def send_wait_for_reply(self, message_type=None, args=None, message=None, retries=5, timeout=5, raw=False, reply_expected=None):
        if not self.run:
            return None
        
        if message is None and message_type is not None:
            message = message_type.build(dict(fields=dict(value=args)))

        while retries >= 0:
            retries -= 1

            if message is not None:
                if LOGGING_DUMP_PACKETS:
                    m = "PC -> A "
                    for c in message:
                        m += "{0:02x} ".format(c)
                    logger.debug(m)
            
            
            with serial_lock:
                if message is not None:
                    self.connection.timeout(timeout)
                    self.connection.write(message)
                data = self.connection.read()
                if raw:
                    return data

            # Retry if no data was available
            if data is None or len(data) == 0:
                if message is None:
                    return None

                time.sleep(0.25)
                continue

            if LOGGING_DUMP_PACKETS:
                m = "PC <- A "
                for c in data:
                    m += "{0:02x} ".format(c)
                logger.debug(m)

            try:
                recv_message = msg.parse(data)
            except:
                recv_message = None

            if recv_message is None:
                logging.exception("Error parsing message")
                time.sleep(0.25)
                continue

            if LOGGING_DUMP_MESSAGES:
                logger.debug(recv_message)

            # Events are async
            if recv_message.fields.value.po.command == 0xe:
                try:
                    self.handle_event(recv_message)
                except:
                    logger.exception("Handle event")

                time.sleep(0.25)
                continue
            
            if recv_message.fields.value.po.command == 0x70:
                self.handle_error(recv_message)
                return None

            if reply_expected is not None and recv_message.fields.value.po.command != reply_expected:
                logging.error("Got message {} but expected {}".format(recv_message.fields.value.po.command, reply_expected))
                logging.error("Detail:\n{}".format(recv_message))
                time.sleep(0.25)
                continue

            return recv_message

        return None

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        partition_template = dict() # Will be populated after status message

        zone_template = dict()

        output_template = dict(
            on=False,
            pulse=False,
            tamper=False,
            supervision_trouble=False,
            timestamp=0)

        self.load_labels(
            self.partitions,
            self.labels['partition'],
            MEM_PARTITION_START,
            MEM_PARTITION_END,
            PARTITIONS,
            template=partition_template)
        self.load_labels(
            self.zones,
            self.labels['zone'],
            MEM_ZONE_START,
            MEM_ZONE_END,
            ZONES,
            template=zone_template)
        self.load_labels(
            self.outputs,
            self.labels['output'],
            MEM_OUTPUT_START,
            MEM_OUTPUT_END,
            OUTPUTS,
            template=output_template)

        for k,v in self.partitions.items():
            self.interface.change('partition', self.partitions[k]['label'], k, v, initial=True)

        for k, v in self.zones.items():
            self.interface.change('zone', self.zones[k]['label'], k, v, initial=True)

        for k, v in self.outputs.items():
                self.interface.change('output', self.outputs[k]['label'], k, v, initial=True)

        # DUMP Labels to console
        logger.debug("Labels updated")
        logger.debug("Partitions: {}".format(list(self.labels['partition'])))
        logger.debug("Zones: {}".format(self.labels['zone']))
        logger.debug("Outputs: {}".format(list(self.labels['output'])))

    def load_labels(self,
                    labelDictIndex,
                    labelDictName,
                    start,
                    end,
                    limit=range(1, 17),
                    template=dict(label='')):
        """Load labels from panel"""
        i = 1
        address = start
        if len(limit) == 0:
            return
        
        while address <= end and i <= max(limit):
            args = dict(address=address)
            reply = self.send_wait_for_reply(msg.ReadEEPROM, args, reply_expected=0x05)
            
            if reply is None:
                logger.error("Could not fully load labels")
                return

            payload = reply.fields.value.data

            for j in [0, 16]:
                label = payload[j:j + 16].strip().decode('latin').replace(" ","_")
                
                if label not in labelDictName and i in limit:
                    properties = template.copy()
                    properties['label'] = label
                    if i in labelDictIndex:
                        labelDictIndex[i] = properties
                    else:
                        labelDictIndex[i] = properties

                    labelDictName[label] = i
                i += 1
            address += MEM_STEP

    def control_zone(self, zone, command):
        logger.debug("Control Zone: {} - {}".format(zone, command))

        if command not in ['bypass', 'clear_bypass']:
            return False

        zones_selected = []
        # if all or 0, select all
        if zone == 'all' or zone == '0':
            zones_selected = list(self.zones)
        else:
            # if set by name, look for it
            if zone in self.labels['zone']:
                zones_selected = [self.labels['zone'][zone]]
            # if set by number, look for it
            elif zone.isdigit():
                number = int(zone)
                if number in self.zones:
                    zones_selected = [number]

        # Not Found
        if len(zones_selected) == 0:
            return False

        value = command=='bypass'
        
        # Apply state changes
        accepted = False
        for e in zones_selected:
            if self.zones[e]['bypass'] == value:
                continue

            args = dict(zone=e)
            reply = self.send_wait_for_reply(msg.ZoneStateCommand, args, reply_expected=0x04)
            
            if reply is not None:
                accepted = True
                self.update_properties('zone', self.zones, e, dict(bypass=value))

        return accepted

    def control_partition(self, partition, command):
        logger.debug("Control Partition: {} - {}".format(partition, command))
        
        if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
            return False
        
        partitions_selected = []
        # if all or 0, select all
        if partition == 'all' or partition == '0':
            partitions_selected = list(self.partitions)
        else:
            # if set by name, look for it
            if partition in self.labels['partition']:
                partitions_selected = [self.labels['partition'][partition]]
            # if set by number, look for it
            elif partition.isdigit():
                number = int(partition)
                if number in self.partitions:
                    partitions_selected = [number]

        # Not Found
        if len(partitions_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        for e in partitions_selected:
            args = dict(partition=e, state=command)
            reply = self.send_wait_for_reply(msg.PartitionStateCommand, args, reply_expected=0x04)

            if reply is not None:
                accepted = True
                if command in ['arm_stay', 'arm_sleep']:
                    self.update_properties('partition', self.partitions, e, {command: True})
                else:
                    self.update_properties('partition', self.partitions, e, {'arm': False, 'arm_stay': False, 'arm_sleep': False})

        return accepted

    def control_output(self, output, command):
        logger.debug("Control Partition: {} - {}".format(output, command))

        if command not in ['on', 'off', 'pulse']:
            return False

        outputs = []
        # if all or 0, select all
        if output == 'all' or output == '0':
            outputs = list(range(1, len(self.outputs)))
        else:
            # if set by name, look for it
            if output in self.labels['output']:
                outputs = [self.labels['output'][output]]
            # if set by number, look for it
            elif output.isdigit():
                number = int(output)
                if number > 0 and number < len(self.outputs):
                    outputs = [number]

        # Not Found
        if len(outputs) == 0:
            return False
        
        accepted = False

        for e in outputs:
            if command == 'pulse':
                args = dict(output=e, state='on')
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

                time.sleep(1)
                args = dict(output=e, state='off')
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True
            else:
                args = dict(output=e, state=command)
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

        return accepted

    def handle_event(self, message):
        """Process Live Event Message and dispatch it to the interface module"""
        event = message.fields.value.event
        logger.debug("Handle Event: {}".format(event))
        
        new_event = self.process_event(event)
        
        self.generate_event_notifications(new_event)

        # Publish event
        if self.interface is not None:
            self.interface.event(raw=new_event)
        

    
    def generate_event_notifications(self, event):
        major_code = event['major'][0]
        minor_code = event['minor'][0]

        # IGNORED

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
        
        # Software Log on
        if major_code == 48 and minor_code == 2:
            return

        
        ## CRITICAL Events

        # Fire Delay Started
        # Zone in Alarm
        # Fire Alarm
        # Zone Alarm Restore
        # Fire Alarm Restore
        # Zone Tampered
        # Zone Tamper Restore
        # Non Medical Alarm
        if major_code in [24, 36, 37, 38, 39, 40, 42, 43, 57] or \
            ( major_code in [44, 45] and minor_code in [1, 2, 3, 4, 5, 6, 7]):
            # Zone Alarm Restore
            #if major_code in [36, 38]:
            
                #detail = self.zones[event['minor'][0]]['label']
            #else:
            detail = event['minor'][1]

            self.interface.notify("Paradox", "{} {}".format(event['major'][1], detail), logging.CRITICAL)
        
        # Silent Alarm
        # Buzzer Alarm
        # Steady Alarm
        # Pulse Alarm
        # Strobe
        # Alarm Stopped
        # Entry Delay
        elif major_code == 2:
            if minor_code in [2, 3, 4, 5, 6, 7, 13]:
                zones_in_alarm = []
                for i in range(1, len(self.zones)):
                    if 'in_alarm' in self.zones[i] and self.zones[i]['in_alarm']:
                        zones_in_alarm.append(self.zones[i]['label'])
                
                self.interface.notify("Paradox", "{} zones: {}".format(event['minor'][1], ','.join(zones_in_alarm)), logging.CRITICAL)
                
            elif minor_code == 13:
                zones_open = []
                for i in range(1, len(self.zones)):
                    if 'open' in self.zones[i] and self.zones[i]['open']:
                        zones_open.append(self.zones[i]['label'])

                self.interface.notify("Paradox", "{} open: {}".format(event['minor'][1], ','.join(zones_open)), logging.INFO)

        # Special Alarm, New Trouble and Trouble Restore
        elif major_code in [40, 44, 45] and minor_code in [1, 2, 3, 4, 5, 6, 7]:
            self.interface.notify("Paradox", "{}: {}".format(event['major'][1], event['minor'][1]), logging.CRITICAL)
        # Signal Weak
        elif major_code in [18, 19, 20, 21]:
            if event['minor'][0] >= 0 and event['minor'][0] < len(self.zones):
                label = self.zones[event['minor'][0]]['label']
            else:
                label = event['minor'][1]
            
            self.interface.notify("Paradox", "{}: {}".format(event['major'][1], label), logging.INFO)
        else:
            # Remaining events trigger lower level notifications
            self.interface.notify("Paradox", "{}: {}".format(event['major'][1], event['minor'][1]), logging.INFO)


    def process_event(self, event):

        major = event['major'][0]
        minor = event['minor'][0]

        change = None

        # ZONES
        if major in (0, 1):
            change=dict(open=(major==1))
        elif major == 35:
            change=dict(bypass=not self.zones[minor])
        elif major in (36, 38):
            change=dict(alarm=(major==36))
        elif major in (37, 39):
            change=dict(fire_alarm=(major==37))
        elif major == 41:
            change=dict(shutdown=True)
        elif major in (42, 43):
            change=dict(tamper=(major==42))
        elif major in (49, 50):
            change=dict(low_battery=(major==49))
        elif major in (51, 52):
            change=dict(supervision_trouble=(major==51))
        
        # PARTITIONS
        elif major == 2:
            if minor in (2, 3, 4, 5, 6):
                change=dict(alarm=True)
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
                change=dict(bell=(minor==1))
        elif major == 6:
            if minor == 3:
                change = dict(arm=True, arm_full=False, arm_sleep=False, arm_stay=True, alarm=False)
            elif minor == 4:
                change = dict(arm=True, arm_full=False, arm_sleep=True, arm_stay=False, alarm=False)  
        # Wireless module
        elif major in (53, 54):
            change = dict(supervision_trouble=(major==53))
        elif major in (53, 56):
            change = dict(tamper_trouble=(major==55))

        new_event = {'major': event['major'], 'minor': event['minor'], 'type': event['type'] }
        
        if change is not None:
            if event['type'] == 'Zone' and len(self.zones) > 0 and minor < len(self.zones):
                self.update_properties('zone', self.zones, minor, change)
                new_event['minor'] = (minor, self.zones[minor]['label'])
            elif event['type'] == 'Partition' and len(self.partitions) > 0:
                pass
                #self.update_properties('partition', self.partitions, minor, change)
                #new_event['minor'] = (minor, self.partitions[minor]['label'])
            elif event['type'] == 'Output' and len(self.outputs) and minor < len(self.outputs):
                self.update_properties('output', self.outputs, minor, change)
                new_event['minor'] = (minor, self.outputs[minor]['label'])

        return new_event


    def update_properties(self, element_type, element_list, index, change):
        #logger.debug("Update Properties {} {} {}".format(element_type, index, change))
        if index < 0 or index >= (len(element_list) + 1):
            logger.debug("Index {} not in element_list {}".format(index, element_list))            
            return

        # Publish changes and update state
        for k, v in change.items():
            old = None
            if k in element_list[index]:
                old = element_list[index][k]
        
                if old != change[k]:
                    logger.debug("Change {}/{}/{} from {} to {}".format(element_type, element_list[index]['label'], k, old, change[k]))
                    element_list[index][k] = change[k]
                    self.interface.change(element_type, element_list[index]['label'],
                                          k, change[k], initial=False)

                    # Trigger notifications for Partitions changes
                    # Ignore some changes as defined in the configuration
                    if element_type == "partition" and k not in PARTITIONS:
                        self.interface.notify("Paradox", "{} {} {}".format(element_list[index]['label'], k, change[k]), logging.INFO)

            else:
                element_list[index][k] = v # Initial value
                self.interface.change(element_type, element_list[index]['label'],
                                          k, change[k], initial=True)

    def handle_status(self, message):
        """Handle MessageStatus"""
        
        if message.fields.value.status_request == 0:
            self.power.update(
                dict(
                    vdc=message.fields.value.vdc,
                    battery=message.fields.value.battery,
                    dc=message.fields.value.dc))

            if time.time() - self.last_power_update > POWER_UPDATE_INTERVAL:
                self.last_power_update = time.time()
                self.interface.change('system','power','vdc', round(message.fields.value.vdc,2), False)
                self.interface.change('system','power','battery', round(message.fields.value.battery,2), False)
                self.interface.change('system','power','dc', round(message.fields.value.dc,2), False)

            i = 1
            while i in ZONES and i in value.zone_open_status:
                zone_open = message.fields.value.zone_open_status[i]
                zone_fire = message.fields.value.zone_fire_status[i]
                zone_tamper = message.fields.value.zone_tamper_status[i]
                self.update_properties('zone', self.zones, i, dict(open=zone_open, fire=zone_fire, tamper=zone_tamper))
                i += 1
            
        elif message.fields.value.status_request == 1:
            i = 1
            while i in PARTITIONS and i in message.fields.value.partition_status:
                v = message.fields.value.partition_status[i]
                self.update_properties('partition', self.partitions, i, v)
                i += 1
            
            i = 1
            while i in ZONES and i in message.fields.value.zone_rf_supervision_trouble:
                rf_supervision = message.fields.value.zone_rf_supervision_trouble[i]
                rf_battery = message.fields.value.zone_rf_low_battery_trouble[i]

                self.update_properties('zone', self.zones, i, dict(
                        rf_supervision_trouble=rf_supervision, 
                        rf_low_battery_trouble=rf_battery))

                i += 1

        elif message.fields.value.status_request == 2:
            i = 1
            while i in ZONES and i in message.fields.value.zone_status:
                v = message.fields.value.zone_status[i]
                self.update_properties('zone', self.zones, i, v)
                i += 1
        
        elif message.fields.value.status_request == 3:
            i = 1
            while i in ZONES and i in message.fields.value.zone_signal_strength:
                v = message.fields.value.zone_signal_strength[i]
                self.update_properties('zone', self.zones, i, dict(signal_strength=v))
                i += 1
        
        elif message.fields.value.status_request == 4:
            #Not Implemented. PGM, Repeaterr, Keypad Signal Strength
            pass

        elif message.fields.value.status_request == 5:
            i = 1
            while i in ZONES and i in message.fields.value.zone_exit_delay:
                v = message.fields.value.zone_exit_delay[i]
                self.update_properties('zone', self.zones, i, dict(exit_delay=v))
                i += 1

    def handle_error(self, message):
        """Handle ErrorMessage"""
        logger.warn("Got Message: {}".format(message.fields.value.message))
        self.run = False

    def disconnect(self):
        reply = self.send_wait_for_reply(msg.TerminateConnection, None, reply_expected=0x05)
        
        if reply is not None:
            logger.info("Disconnected: {}".format(reply.fields.value.message))

        self.run = False
