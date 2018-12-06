# -*- coding: utf-8 -*-

from paradox.hardware import create_panel
import logging
import time
from threading import Lock
import datetime
import binascii

from config import user as cfg

logger = logging.getLogger('PAI').getChild(__name__)

PARTITION_ACTIONS = dict(arm=0x04, disarm=0x05, arm_stay=0x01, arm_sleep=0x03,  arm_stay_stayd=0x06, arm_sleep_stay=0x07, disarm_all=0x08)
ZONE_ACTIONS = dict(bypass=0x10, clear_bypass=0x10)
PGM_ACTIONS = dict(on_override=0x30, off_override=0x31, on=0x32, off=0x33, pulse=0)

serial_lock = Lock()

STATE_STOP = 0
STATE_RUN = 1
STATE_PAUSE = 2
STATE_ERROR = 3


class Paradox:
    def __init__(self,
                 connection,
                 interface,
                 retries=3):

        self.panel = None
        self.connection = connection
        self.retries = retries
        self.interface = interface
        self.reset()
        self.data = dict(zone=dict(), partition=dict(), pgm=dict(), system=dict())
        self.labels = dict()

    def reset(self):

        # Keep track of alarm state
        self.data = dict(zone=dict(), partition=dict(), pgm=dict(), 
            system=dict(power=dict(label='power'), rf=dict(label='rf'), troubles=dict(label='troubles'))
        )

        self.last_power_update = 0
        self.run = STATE_STOP
        self.loop_wait = True
        self.labels = dict()
        self.status_cache = dict()

    def connect(self):
        logger.info("Connecting to interface")
        if not self.connection.connect():
            logger.error('Failed to connect to interface')
            self.run = STATE_STOP
            return False

        self.connection.timeout(0.5)

        logger.info("Connecting to panel")

        # Reset all states
        self.reset()

        self.run = STATE_RUN

        if not self.panel:
            self.panel = create_panel(self)

        try:
            logger.info("Initiating communication")
            reply = self.send_wait(self.panel.get_message('InitiateCommunication'), None, reply_expected=0x07)

            if reply:
                logger.info("Found Panel {} version {}.{} build {}".format(
                    (reply.fields.value.label.strip(b'\0 ').decode('utf-8')),
                    reply.fields.value.application.version,
                    reply.fields.value.application.revision,
                    reply.fields.value.application.build))
            else:
                logger.warn("Unknown panel. Some features may not be supported")

            logger.info("Starting communication")
            reply = self.send_wait(self.panel.get_message('StartCommunication'), args=dict(source_id=0x02), reply_expected=0x00)
            
            if reply is None:
                self.run = STATE_STOP
                return False

            self.panel = create_panel(self, reply.fields.value.product_id) # Now we know what panel it is. Let's
            # recreate panel object.

            result = self.panel.initialize_communication(reply, cfg.PASSWORD)
            if not result:
                self.run = STATE_STOP
                return False
            self.send_wait()  # Read WinLoad in (connected) event

            if cfg.SYNC_TIME:
                self.sync_time()
                self.send_wait()  # Read Clock loss restore event

            self.panel.update_labels()
                    
            logger.info("Connection OK")
            self.loop_wait = False

            return True
        except Exception:
            logger.exception("Connect error")

        self.run = STATE_STOP
        return False

    def sync_time(self):
        logger.debug("Synchronizing panel time")

        now = datetime.datetime.now()
        args = dict(century=int(now.year / 100), year=int(now.year % 100), month=now.month, day=now.day, hour=now.hour,minute=now.minute)

        reply = self.send_wait(self.panel.get_message('SetTimeDate'), args, reply_expected=0x03)
        if reply is None:
            logger.warn("Could not set panel time")

        return

    def loop(self):
        logger.debug("Loop start")
        args = {}

        while self.run != STATE_STOP:

            while self.run == STATE_PAUSE:
                time.sleep(5)

            self.loop_wait = True

            tstart = time.time()
            try:
                for i in cfg.STATUS_REQUESTS:
                    reply = self.panel.request_status(i)
                    if reply is not None:
                        tstart = time.time()
                        self.panel.handle_status(reply)
            except ConnectionError:
                raise
            except Exception:
                logger.exception("Loop")

            # cfg.Listen for events
            while time.time() - tstart < cfg.KEEP_ALIVE_INTERVAL and self.run == STATE_RUN and self.loop_wait:
                self.send_wait(None, timeout=min(time.time() - tstart, 1))

    def send_wait_simple(self, message=None, timeout=5, wait=True):
        if message is not None:
            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC -> A {}".format(binascii.hexlify(message)))

        with serial_lock:
            if message is not None:
                self.connection.timeout(timeout)
                self.connection.write(message)

            if not wait:
                return None

            data = self.connection.read()

        if cfg.LOGGING_DUMP_PACKETS:
            logger.debug("PC <- A {}".format(binascii.hexlify(data)))

        return data

    def send_wait(self, message_type=None, args=None, message=None, retries=5, timeout=5, reply_expected=None):

        if message is None and message_type is not None:
            message = message_type.build(dict(fields=dict(value=args)))

        while retries >= 0:
            retries -= 1

            if message is not None and cfg.LOGGING_DUMP_PACKETS:
                    logger.debug("PC -> A {}".format(binascii.hexlify(message)))

            with serial_lock:
                if message is not None:
                    self.connection.timeout(timeout)
                    self.connection.write(message)

                data = self.connection.read()

            # Retry if no data was available
            if data is None or len(data) == 0:
                if message is None:
                    return None
                continue

            if cfg.LOGGING_DUMP_PACKETS:
                logger.debug("PC <- A {}".format(binascii.hexlify(data)))

            try:
                recv_message = self.panel.parse_message(data)
                # No message
                if recv_message is None:
                    logger.debug("Unknown message: %s" % (" ".join("{:02x} ".format(c) for c in data)))
                    continue
            except Exception:
                logging.exception("Error parsing message")
                continue

            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug(recv_message)

            # Events are async
            if recv_message.fields.value.po.command == 0xe: # Events
                try:
                    self.handle_event(recv_message)

                except Exception:
                    logger.exception("Handle event")

                # Prevent events from blocking further messages
                if message is None:
                    return None

                retries += 1  # Ignore this try

            elif recv_message.fields.value.po.command == 0x70: # Terminate connection
                self.handle_error(recv_message)
                return None

            elif reply_expected is not None and recv_message.fields.value.po.command != reply_expected:
                logging.error("Got message {} but expected {}".format(recv_message.fields.value.po.command, reply_expected))
                logging.error("Detail:\n{}".format(recv_message))
            else:
                return recv_message

        return None

    def control_zone(self, zone, command):
        logger.debug("Control Zone: {} - {}".format(zone, command))

        if command not in ZONE_ACTIONS:
            return False

        zones_selected = []
        # if all or 0, select all
        if zone == 'all' or zone == '0':
            zones_selected = list(self.data['zone'])
        else:
            # if set by name, look for it
            if zone in self.labels['zone']:
                zones_selected = [self.labels['zone'][zone]]
            # if set by number, look for it
            elif zone.isdigit():
                number = int(zone)
                if number in self.data['zone']:
                    zones_selected = [number]

        # Not Found
        if len(zones_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        for e in zones_selected:
            args = dict(action=ZONE_ACTIONS[command], argument=(e - 1))
            reply = self.send_wait(self.panel.get_message('PerformAction'), args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        # Refresh status
        self.loop_wait = False
        return accepted

    def control_partition(self, partition, command):
        logger.debug("Control Partition: {} - {}".format(partition, command))

        if command not in PARTITION_ACTIONS:
            return False

        partitions_selected = []

        # if all or 0, select all
        if partition == 'all' or partition == '0':
            partitions_selected = list(self.data['partition'])
        else:
            # if set by name, look for it
            if partition in self.labels['partition']:
                partitions_selected = [self.labels['partition'][partition]]
            # if set by number, look for it
            elif partition.isdigit():
                number = int(partition)
                if number in self.data['partition']:
                    partitions_selected = [number]

        # Not Found
        if len(partitions_selected) == 0:
            return False

        # Apply state changes
        accepted = False

        for e in partitions_selected:
            args = dict(action=PARTITION_ACTIONS[command], argument=(e - 1))
            reply = self.send_wait(self.panel.get_message('PerformAction'), args, reply_expected=0x04)

            if reply is not None:
                accepted = True

        # Refresh status
        self.loop_wait = False

        return accepted

    def control_output(self, output, command):
        logger.debug("Control Partition: {} - {}".format(output, command))

        if command not in PGM_ACTIONS:
            return False

        outputs = []
        # if all or 0, select all
        if output == 'all' or output == '0':
            outputs = list(range(1, len(self.data['pgm'])))
        else:
            # if set by name, look for it
            if output in self.labels['pgm']:
                outputs = [self.labels['pgm'][output]]
            # if set by number, look for it
            elif output.isdigit():
                number = int(output)
                if number > 0 and number < len(self.data['pgm']):
                    outputs = [number]

        # Not Found
        if len(outputs) == 0:
            return False

        accepted = False

        for e in outputs:
            if command == 'pulse':
                args = dict(action=PGM_COMMAND['on'], argument=(e - 1))
                reply = self.send_wait(self.panel.get_message('PerformAction'), args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

                time.sleep(1)
                args = dict(action=PGM_COMMAND['off'], argument=(e - 1))
                reply = self.send_wait(self.panel.get_message('PerformAction'), args, reply_expected=0x04)
                if reply is not None:
                    accepted = True
            else:
                args = dict(action=PGM_COMMAND[command], argument=(e - 1))
                reply = self.send_wait(self.panel.get_message('PerformAction'), args, reply_expected=0x04)
                if reply is not None:
                    accepted = True

        # Refresh status
        self.loop_wait = False

        return accepted

    def handle_event(self, message):
        """Process cfg.Live Event Message and dispatch it to the interface module"""
        event = message.fields.value.event
        logger.debug("Handle Event: {}".format(event))

        new_event = self.panel.process_event(event)

        self.panel.generate_event_notifications(new_event)

        # Publish event
        if self.interface is not None:
            self.interface.event(raw=new_event)

    def update_properties(self, element_type, key, change, force_publish=False):
        try:
            elements = self.data[element_type]
        except KeyError:
            logger.debug('Error: "%s" key is missing from data' % element_type)
            return

        if key not in elements:
            return

        # Publish changes and update state
        for property_name, property_value in change.items():
            old = None

            if property_name.startswith('_'): # skip private properties
                continue

            # Virtual property "Trouble"
            # True if element has ANY type of alarm
            if 'trouble' in property_name and property_name != 'trouble':
                if property_value:
                    self.update_properties(element_type, key, dict(trouble=True))
                else:
                    r = False
                    for kk, vv in elements[key].items():
                        if 'trouble' in kk:
                            r = r or elements[key][kk]

                    self.update_properties(element_type, key, dict(trouble=r), force_publish=force_publish)

            if property_name in elements[key]:
                old = elements[key][property_name]

                if old != change[property_name] or force_publish or cfg.PUSH_UPDATE_WITHOUT_CHANGE:
                    logger.debug("Change {}/{}/{} from {} to {}".format(element_type, elements[key]['label'], property_name, old, property_value))
                    elements[key][property_name] = property_value
                    self.interface.change(element_type, elements[key]['label'],
                                          property_name, property_value, initial=False)

                    # Trigger notifications for Partitions changes
                    # Ignore some changes as defined in the configuration
                    try:
                        if (element_type == "partition" and key in cfg.LIMITS['partition']  and property_name not in cfg.PARTITIONS_CHANGE_NOTIFICATION_IGNORE) \
                            or ('trouble' in property_name):
                            self.interface.notify("Paradox", "{} {} {}".format(elements[key]['label'], property_name, property_value), logging.INFO)
                    except KeyError:
                        logger.debug("Key 'partition' doesn't exist in cfg.LIMITS")
                    except:
                        logger.exception("Trigger notifications")

            else:
                elements[key][property_name] = property_value  # Initial value
                surpress = 'trouble' not in property_name

                self.interface.change(element_type, elements[key]['label'],
                                      property_name, property_value, initial=surpress)

    def handle_error(self, message):
        """Handle ErrorMessage"""
        logger.warn("Got ERROR Message: {}".format(message.fields.value.message))
        self.run = STATE_STOP

    def disconnect(self):
        if self.run == STATE_RUN:
            logger.info("Disconnecting from the Alarm Panel")
            self.run = STATE_STOP
            self.loop_wait = False
            reply = self.send_wait(self.panel.get_message('CloseConnection'), None, reply_expected=0x07)
            self.connection.close()
            
    def pause(self):
        if self.run == STATE_RUN:
            logger.info("Disconnecting from the Alarm Panel")
            self.run = STATE_PAUSE
            self.loop_wait = False
            reply = self.send_wait(self.panel.get_message('CloseConnection'), None, reply_expected=0x07)
            self.connection.close()
            
    def resume(self):
        if self.run == STATE_PAUSE:
            self.connect()
