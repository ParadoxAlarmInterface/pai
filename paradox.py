import paradox_messages as msg
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
MEM_ZONE_END = MEM_ZONE_START + 0x10 * ZONES
MEM_OUTPUT_START = 0x210
MEM_OUTPUT_END = MEM_OUTPUT_START + 0x10 * OUTPUTS
MEM_PARTITION_START = 0x310
MEM_PARTITION_END = 0x310
MEM_STEP = 0x10

serial_lock = Lock()

class Paradox:
    def __init__(self,
                 connection,
                 interface,
                 retries=3,
                 alarmeventmap="ParadoxMG5050"):

        self.connection = connection
        self.connection.timeout(0.5)
        self.retries = retries
        self.alarmeventmap = alarmeventmap
        self.interface = interface

        # Keep track of alarm state
        self.labels = {'zone': {}, 'partition': {}, 'output': {}}
        self.zones = []
        self.partitions = []
        self.outputs = []
        self.power = dict()
        self.run = False

    def connect(self):
        logger.info("Connecting to panel")

        try:
            reply = self.send_wait_for_reply(msg.InitiateCommunication, None)

            if reply is None:
                return False

            logging.info("Found Panel {} version {}.{} build {}".format(
                (reply.fields.value.label.decode('latin').strip()),
                reply.fields.value.application.version,
                reply.fields.value.application.revision,
                reply.fields.value.application.build))
            reply = self.send_wait_for_reply(msg.SerialInitialization, None)
            if reply is None:
                return False

            reply = self.send_wait_for_reply(
                message=reply.fields.data + reply.checksum)

            if reply is None:
                return False

            logger.info("Connected!")

            self.update_labels()
            
            self.run = True

            return True
        except:
            logger.exception("Connect error")

        return False

    def loop(self):
        logger.debug("Loop start")
        args = {}

        while self.run:
            logger.debug("Getting alarm status")
            
            tstart = time.time()

            i = 0
            while i < 3:
                args = dict(address=MEM_STATUS_BASE1 + i)
                reply = self.send_wait_for_reply(msg.Upload, args)
                if reply is not None:
                    self.handle_status(reply)

                i += 1

            # Listen for events
            while time.time() - tstart < KEEP_ALIVE_INTERVAL: 
                self.send_wait_for_reply(None)

    def send_wait_for_reply(self, message_type=None, args=None, message=None, retries=5):
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
                    self.connection.write(message)
            
                data = self.connection.read()

            # Retry if no data was available
            if data is None or len(data) == 0:
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
                logging.exception("Error parsing message")
                time.sleep(0.25)
                continue

            if LOGGING_DUMP_MESSAGES:
                logger.debug(recv_message)

            # Events are async
            if recv_message.fields.value.po.command == 0xe:
                self.handle_event(recv_message)
                time.sleep(0.25)
                continue

            return recv_message

        return None

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        partition_template = dict(
            alarm=False,
            arm=False,
            arm_full=False,
            arm_sleep=False,
            arm_stay=False,
            alarm_fire=False,
            alarm_audible=False,
            alarm_silent=False)
        zone_template = dict(
            open=False,
            bypass=False,
            alarm=False,
            fire_alarm=False,
            shutdown=False,
            tamper=False,
            low_battery=False,
            supervision_trouble=False,
            in_alarm=False,
            tx_delay=False,
            entry_delay=False,
            intellizone_delay=False,
            generated_alarm=False)
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

        for i in range(1, len(self.partitions)):
            partition = self.partitions[i]
            for k, v in partition.items():
                self.interface.change('partition', self.partitions[i]['label'], k, v, initial=True)

        for i in range(1, len(self.zones)):
            zone = self.zones[i]
            for k, v in zone.items():
                self.interface.change('zone', self.zones[i]['label'], k, v, initial=True)

        for i in range(1, len(self.outputs)):
            output = self.outputs[i]
            for k, v in output.items():
                self.interface.change('output', self.outputs[i]['label'], k, v, initial=True)

        # DUMP Labels to console
        logger.debug("Labels updated")

        aux = []
        for c in self.partitions[1:]:
            aux.append(c['label'])
        logger.debug("Partitions: {}".format(aux))

        aux = []
        for c in self.zones[1:]:
            aux.append(c['label'])
        logger.debug("Zones: {}".format(aux))

        aux = []
        for c in self.outputs[1:]:
            aux.append(c['label'])
        logger.debug("Outputs: {}".format(aux))

    def load_labels(self,
                    labelList,
                    labelDict,
                    start,
                    end,
                    limit=16,
                    template=dict(label='')):
        """Load labels from panel"""
        i = 1
        labelList.append("all")
        address = start
        while address <= end and len(labelList) - 1 < limit:
            args = dict(address=address)
            reply = self.send_wait_for_reply(msg.Upload, args)

            payload = reply.fields.value.data

            for j in [0, 16]:
                label = payload[j:j + 16].strip().decode('latin').replace(" ","_")

                if label not in labelDict.keys() and len(labelList) - 1 < limit:
                    properties = template.copy()
                    properties['label'] = label
                    if len(labelList) <= i:
                        labelList.append(properties)
                    else:
                        labelList[i] = properties

                    labelDict[label] = i
                    i += 1
            address += MEM_STEP

    def control_zone(self, zone, command):
        logger.debug("Control Zone: {} - {}".format(zone, command))

        if command not in ['bypass', 'clear_bypass']:
            return False

        zones_selected = []
        # if all or 0, select all
        if zone == 'all' or zone == '0':
            zones_selected = list(range(1, len(self.zones)))
        else:
            # if set by name, look for it
            if zone in self.labels['zone']:
                zones_selected = [self.labels['zone'][zone]]
            # if set by number, look for it
            elif zone.isdigit():
                number = int(zone)
                if number > 0 and number < len(self.zones):
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
            reply = self.send_wait_for_reply(msg.ZoneStateCommand, args)
            
            if reply is not None and reply.fields.value.po.command == 0x04:
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
            partitions_selected = list(range(1, len(self.partitions)))
        else:
            # if set by name, look for it
            if partition in self.labels['partition']:
                partitions_selected = [self.labels['partition'][partition]]
            # if set by number, look for it
            elif partition.isdigit():
                number = int(partition)
                if number > 0 and number < len(self.partitions):
                    partitions_selected = [number]

        # Not Found
        if len(partitions_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        for e in partitions_selected:
            args = dict(partition=e, state=command)
            reply = self.send_wait_for_reply(msg.PartitionStateCommand, args)

            if reply is not None and reply.fields.value.po.command == 0x04:
                accepted = True
                if command in ['arm_stay', 'arm_sleep']:
                    self.update_properties('partition', self.partitions, e, {'arm': True})
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
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args)
                if reply is not None and reply.fields.value.po.command == 0x04:
                    accepted = True

                time.sleep(1)
                args = dict(output=e, state='off')
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args)
                if reply is not None and reply.fields.value.po.command == 0x04:
                    accepted = True
            else:
                args = dict(output=e, state=command)
                reply = self.send_wait_for_reply(msg.OutputStateCommand, args)
                if reply is not None and reply.fields.value.po.command == 0x04:
                    accepted = True

        return accepted

    def handle_event(self, message):
        """Process Live Event Message and dispatch it to the interface module"""
        event = message.fields.value.event
        logger.debug("Handle Event: {}".format(event))

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
            elif event['type'] == 'Partition' and len(self.partitions) > 0 and minor < len(self.partitions):
                self.update_properties('partition', self.partitions, minor, change)
                new_event['minor'] = (minor, self.partitions[minor]['label'])
            elif event['type'] == 'Output' and len(self.outputs) and minor < len(self.outputs):
                self.update_properties('output', self.outputs, minor, change)
                new_event['minor'] = (minor, self.outputs[minor]['label'])

        # Publish event
        if self.interface is not None:
            self.interface.event(
                raw=new_event)

    def update_properties(self, element_type, element_list, index, change):
        logger.debug("Update Properties {} {} {}".format(element_type, index, change))
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
                                      k, change[k])


    def handle_status(self, message):
        """Handle MessageStatus"""
   
        if message.fields.value.po.command != 0x05:
            return
        
        logger.debug("Handle Status")
        if LOGGING_DUMP_MESSAGES:
            logger.debug("{}".format(message))

        if message.fields.value.address == 0:
            self.power.update(
                dict(
                    vdc=message.fields.value.vdc,
                    battery=message.fields.value.battery,
                    dc=message.fields.value.dc))

            i = 1
            while i <= ZONES and i in message.fields.value.zone_status:
                v = message.fields.value.zone_status[i]
                self.update_properties('zone', self.zones, i, v)
                i += 1

        elif message.fields.value.address == 1:
            i = 1
            while i <= PARTITIONS and i in message.fields.value.partition_status:
                v = message.fields.value.partition_status[i]
                logger.debug("Partition Status {}".format(v))
                self.update_properties('partition', self.partitions, i, v)
                i += 1

        elif message.fields.value.address == 2:
            i = 1
            while i <= ZONES and i in message.fields.value.zone_status:
                v = message.fields.value.zone_status[i]
                self.update_properties('zone', self.zones, i, v)
                i += 1

    def disconnect(self):
        reply = self.send_wait_for_reply(msg.TerminateConnection, None)
        if reply is not None and reply.fields.value.message == 0x05:
            logger.info("Disconnected: {}".format(reply.fields.value.message))
        else:
            logger.error("Got error from panel: {}".format(reply.fields.value.message))

        self.run = False
