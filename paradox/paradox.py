# -*- coding: utf-8 -*-

import binascii
import logging
import time
from collections import defaultdict, MutableMapping
from threading import Lock
from typing import Optional, Sequence, Iterable

from construct import Container

from paradox.hardware import create_panel
from paradox import event
from enum import Enum

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

serial_lock = Lock()

STATE_STOP = 0
STATE_RUN = 1
STATE_PAUSE = 2
STATE_ERROR = 3


class NotifyPropertyChange(Enum):
    NO = 0
    DEFAULT = 1
    YES = 2


class PublishPropertyChange(Enum):
    NO = 0
    DEFAULT = 1
    YES = 2


class Type(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.store = dict()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        if isinstance(key, str):
            for k, v in self.items():
                if "key" in v and v["key"] == key:
                    return v
        return self.store[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    @staticmethod
    def __keytransform__(key):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key


class Paradox:

    def __init__(self,
                 connection,
                 interface,
                 retries=3):

        self.panel = None  # type: Panel
        self.connection = connection
        self.retries = retries
        self.interface = interface

        self.data = defaultdict(Type)  # dictionary of Type
        self.reset()

    def reset(self):

        # Keep track of alarm state
        self.data['system'] = dict(power=dict(label='power', key='power', id=0),
                                   rf=dict(label='rf', key='rf', id=1),
                                   troubles=dict(label='troubles', key='troubles', id=2))

        self.last_power_update = 0
        self.run = STATE_STOP
        self.loop_wait = True
        self.status_cache = dict()

    def connect(self):
        logger.info("Connecting to interface")
        if not self.connection.connect():
            logger.error('Failed to connect to interface')
            self.run = STATE_STOP
            return False

        self.run = STATE_STOP

        self.connection.timeout(0.5)

        logger.info("Connecting to panel")

        # Reset all states
        self.reset()

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
            reply = self.send_wait(self.panel.get_message('StartCommunication'),
                                   args=dict(source_id=0x02), reply_expected=0x00)

            if reply is None:
                return False

            self.panel = create_panel(self, reply.fields.value.product_id)  # Now we know what panel it is. Let's
            # recreate panel object.

            result = self.panel.initialize_communication(reply, cfg.PASSWORD)
            if not result:
                return False
            self.send_wait()  # Read WinLoad in (connected) event

            if cfg.SYNC_TIME:
                self.sync_time()
                self.send_wait()  # Read Clock loss restore event

            if cfg.DEVELOPMENT_DUMP_MEMORY:
                if hasattr(self.panel, 'dump_memory') and callable(self.panel.dump_memory):
                    logger.warn("Requested memory dump. Dumping...")
                    self.panel.dump_memory()
                    logger.warn("Memory dump completed. Exiting pai.")
                    raise SystemExit()
                else:
                    logger.warn("Requested memory dump, but current panel type does not support it yet.")

            self.panel.update_labels()

            self.run = STATE_RUN

            logger.info("Connection OK")
            self.loop_wait = False

            return True
        except Exception:
            logger.exception("Connect error")

        self.run = STATE_STOP
        return False

    def sync_time(self):
        logger.debug("Synchronizing panel time")

        now = time.localtime()
        args = dict(century=int(now.tm_year / 100), year=int(now.tm_year % 100),
                    month=now.tm_mon, day=now.tm_mday, hour=now.tm_hour, minute=now.tm_min)

        reply = self.send_wait(self.panel.get_message('SetTimeDate'), args, reply_expected=0x03)
        if reply is None:
            logger.warn("Could not set panel time")

    def loop(self):
        logger.debug("Loop start")

        while self.run != STATE_STOP:

            while self.run == STATE_PAUSE:
                time.sleep(5)

            # May happen when out of sleep
            if self.run == STATE_STOP:
                break

            self.loop_wait = True

            tstart = time.time()
            try:
                for i in cfg.STATUS_REQUESTS:
                    logger.debug("Requesting status: %d" % i)
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

    def send_wait_simple(self, message=None, timeout=5, wait=True) -> Optional[bytes]:
        # Connection closed
        if self.connection is None:
            return

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

    def send_wait(self,
                  message_type=None,
                  args=None,
                  message=None,
                  retries=5,
                  timeout=5.0,
                  reply_expected=None) -> Optional[Container]:

        # Connection closed
        if self.connection is None:
            return

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
                recv_message = self.panel.parse_message(data, direction='frompanel')
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
            if recv_message.fields.value.po.command == 0xe:  # Events
                try:
                    self.handle_event(recv_message)

                except Exception:
                    logger.exception("Handle event")

                # Prevent events from blocking further messages
                if message is None:
                    return None

                retries += 1  # Ignore this try

            elif recv_message.fields.value.po.command == 0x7 and data[1] != 0xff:  # Error
                self.handle_error(recv_message)
                return None

            elif reply_expected is not None:
                if isinstance(reply_expected, Iterable):
                    if any(recv_message.fields.value.po.command == expected for expected in reply_expected):
                        return recv_message
                    else:
                        logging.error(
                            "Got message {} but expected on of [{}]".format(recv_message.fields.value.po.command,
                                                                            ', '.join(reply_expected)))
                        logging.error("Detail:\n{}".format(recv_message))
                else:
                    if recv_message.fields.value.po.command == reply_expected:
                        return recv_message
                    else:
                        logging.error("Got message {} but expected {}".format(recv_message.fields.value.po.command,
                                                                              reply_expected))
                        logging.error("Detail:\n{}".format(recv_message))
            else:
                return recv_message

        return None

    @staticmethod
    def _select(haystack, needle) -> Sequence[int]:
        """
        Helper function to select objects from provided dictionary

        :param haystack: dictionary
        :param needle:
        :return: Sequence[int] list of object indexes
        """
        selected = []  # type: Sequence[int]
        if needle == 'all' or needle == '0':
            selected = list(haystack)
        else:
            if needle.isdigit() and 0 < int(needle) < len(haystack):
                el = haystack.get(int(needle))
            else:
                el = haystack.get(needle)

            if el:
                if "id" not in el:
                    raise Exception("Invalid dictionary of elements provided")
                selected = [el["id"]]

        return selected

    def control_zone(self, zone, command) -> bool:
        logger.debug("Control Zone: {} - {}".format(zone, command))

        zones_selected = self._select(self.data['zone'], zone)  # type: Sequence[int]

        # Not Found
        if len(zones_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = self.panel.control_zones(zones_selected, command)
        except NotImplementedError:
            logger.error('control_zones is not implemented for this alarm type')

        # Refresh status
        self.loop_wait = False

        return accepted

    def control_partition(self, partition, command) -> bool:
        logger.debug("Control Partition: {} - {}".format(partition, command))

        partitions_selected = self._select(self.data['partition'], partition)  # type: Sequence[int]

        # Not Found
        if len(partitions_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = self.panel.control_partitions(partitions_selected, command)
        except NotImplementedError:
            logger.error('control_partitions is not implemented for this alarm type')
        # Apply state changes

        # Refresh status
        self.loop_wait = False

        return accepted

    def control_output(self, output, command) -> bool:
        logger.debug("Control Output: {} - {}".format(output, command))

        outputs_selected = self._select(self.data['pgm'], output)

        # Not Found
        if len(outputs_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = self.panel.control_outputs(outputs_selected, command)
        except NotImplementedError:
            logger.error('control_outputs is not implemented for this alarm type')
        # Apply state changes

        # Refresh status
        self.loop_wait = False

        return accepted

    def get_label(self, label_type, label_id):
        if label_type in self.data:
            el = self.data[label_type].get(label_id)
            if el:
                return el.get("label")

    def handle_event(self, message):
        """Process cfg.Live Event Message and dispatch it to the interface module"""
        evt = event.Event(self.panel.event_map, message, label_provider=self.get_label)

        logger.debug("Handle Event: {}".format(evt))

        # Temporary to catch labels/properties in wrong places
        # TODO: REMOVE
        if evt.type in self.data:
            if not evt.id:
                logger.warn("Missing element ID in {}/{}".format(evt.type, evt.label))
            else:
                el = self.data[evt.type].get(evt.id)
                if not el:
                    logger.warn("Missing element with ID {} in {}/{}".format(evt.id, evt.type, evt.label))
                else:
                    for k in evt.change:
                        if k not in el:
                            logger.warn("Missing property {} in {}/{}".format(k, evt.type, evt.label))
                    if evt.label != el.get("label"):
                        logger.warn(
                            "Labels differ {} != {} in {}/{}".format(el.get("label"), evt.label, evt.type, evt.label))
        else:
            logger.warn("Missing type {} for event: {}.{} {}".format(evt.type, evt.major, evt.minor, evt.message))
        # Temporary end

        if len(evt.change) > 0 and evt.type in self.data and evt.id in self.data[evt.type]:
            self.update_properties(evt.type, evt.id,
                                   evt.change, notify=NotifyPropertyChange.NO)

        # Publish event
        if self.interface is not None:
            self.interface.event(evt)

    def update_properties(self, element_type, type_key, change,
                          notify=NotifyPropertyChange.DEFAULT, publish=PublishPropertyChange.DEFAULT):
        try:
            elements = self.data[element_type]
        except KeyError:
            logger.debug('Error: "%s" key is missing from data' % element_type)
            return

        if type_key not in elements:
            return

        # Publish changes and update state
        for property_name, property_value in change.items():

            if property_name.startswith('_'):  # skip private properties
                continue

            # Virtual property "Trouble"
            # True if element has ANY type of alarm
            if 'trouble' in property_name and property_name != 'trouble':
                if property_value:
                    self.update_properties(element_type, type_key, dict(trouble=True), notify=notify, publish=publish)
                else:
                    r = False
                    for kk, vv in elements[type_key].items():
                        if 'trouble' in kk:
                            r = r or elements[type_key][kk]

                    self.update_properties(element_type, type_key, dict(trouble=r), notify=notify, publish=publish)

            if property_name in elements[type_key]:
                old = elements[type_key][property_name]

                if old != change[property_name] or publish == PublishPropertyChange.YES \
                        or cfg.PUSH_UPDATE_WITHOUT_CHANGE:
                    logger.debug("Change {}/{}/{} from {} to {}".format(element_type,
                                                                        elements[type_key]['key'],
                                                                        property_name,
                                                                        old,
                                                                        property_value))
                    elements[type_key][property_name] = property_value
                    self.interface.change(element_type, elements[type_key]['key'],
                                          property_name, property_value, initial=False)

                    # Trigger notifications for Partitions changes
                    # Ignore some changes as defined in the configuration
                    # TODO: Move this to another place?
                    try:
                        if notify != NotifyPropertyChange.NO and \
                                ((element_type == "partition" and type_key in cfg.LIMITS['partition'] and
                                  property_name not in cfg.PARTITIONS_CHANGE_NOTIFICATION_IGNORE) or
                                 ('trouble' in property_name)):
                            self.interface.notify("Paradox", "{} {} {}".format(elements[type_key]['key'],
                                                                               property_name,
                                                                               property_value), logging.INFO)
                    except KeyError:
                        logger.debug("Key 'partition' doesn't exist in cfg.LIMITS")
                    except Exception:
                        logger.exception("Trigger notifications")

            else:
                elements[type_key][property_name] = property_value  # Initial value
                suppress = 'trouble' not in property_name

                self.interface.change(element_type, elements[type_key]['key'],
                                      property_name, property_value, initial=suppress)

    def handle_error(self, message):
        """Handle ErrorMessage"""
        error_enum = message.fields.value.message

        message = self.panel.get_error_message(error_enum)
        logger.error("Got ERROR Message: {}".format(message))

        self.run = STATE_STOP

    def disconnect(self):
        if self.run == STATE_RUN:
            logger.info("Disconnecting from the Alarm Panel")
            self.run = STATE_STOP
            self.loop_wait = False
            self.send_wait(self.panel.get_message('CloseConnection'), None, reply_expected=0x07)
            self.connection.close()

    def pause(self):
        if self.run == STATE_RUN:
            logger.info("Disconnecting from the Alarm Panel")
            self.run = STATE_PAUSE
            self.loop_wait = False
            self.send_wait(self.panel.get_message('CloseConnection'), None, reply_expected=0x07)

    def resume(self):
        if self.run == STATE_PAUSE:
            self.connect()
