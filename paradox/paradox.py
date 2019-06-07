# -*- coding: utf-8 -*-

import asyncio
import logging
import time
from collections import defaultdict, MutableMapping
from enum import Enum
from threading import Lock
from typing import Optional, Sequence, Iterable, Callable, Awaitable

from construct import Container

from paradox import event
from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.interfaces.interface_manager import InterfaceManager
from paradox.hardware import create_panel
from paradox.lib import ps
from paradox.lib.async_message_manager import AsyncMessageManager, EventMessageHandler, ErrorMessageHandler

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
                 connection: Connection,
                 interface: InterfaceManager,
                 retries=3):

        self.panel = None  # type: Panel
        self.connection = connection
        self.retries = retries
        self.interface = interface
        self.message_manager = AsyncMessageManager()
        self.work_loop = asyncio.get_event_loop() # type: asyncio.AbstractEventLoop
        self.receive_worker_task = None

        self.message_manager.register_handler(EventMessageHandler(self.handle_event))
        self.message_manager.register_handler(ErrorMessageHandler(self.handle_error))

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

    def connect(self) -> bool:
        task = self.work_loop.create_task(self.connect_async())
        self.work_loop.run_until_complete(task)
        return task.result()

    async def connect_async(self):
        self.disconnect()  # socket needs to be also closed

        logger.info("Connecting to interface")
        if not await self.connection.connect():
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
            self.connection.variable_message_length(self.panel.variable_message_length)

        try:
            logger.info("Initiating communication")

            reply = await self.send_wait(self.panel.get_message('InitiateCommunication'), None, reply_expected=0x07)

            if reply:
                logger.info("Found Panel {} version {}.{} build {}".format(
                    (reply.fields.value.label.strip(b'\0 ').decode(cfg.LABEL_ENCODING)),
                    reply.fields.value.application.version,
                    reply.fields.value.application.revision,
                    reply.fields.value.application.build))
            else:
                raise ConnectionError("Panel did not replied to InitiateCommunication")


            logger.info("Starting communication")
            reply = await self.send_wait(self.panel.get_message('StartCommunication'),
                                   args=dict(source_id=0x02), reply_expected=0x00)

            if reply is None:
                raise ConnectionError("Panel did not replied to StartCommunication")

            if reply.fields.value.product_id is not None:
                self.panel = create_panel(self, reply.fields.value.product_id)  # Now we know what panel it is. Let's
                ps.sendMessage('panel_detected', product_id=reply.fields.value.product_id)
            # recreate panel object.

            result = await self.panel.initialize_communication(reply, cfg.PASSWORD)
            if not result:
                raise ConnectionError("Failed to initialize communication")

            # Now we need to start async message reading worker
            self.run = STATE_RUN

            self.receive_worker_task = self.work_loop.create_task(self.receive_worker())

            if cfg.SYNC_TIME:
                await self.sync_time()

            if cfg.DEVELOPMENT_DUMP_MEMORY:
                if hasattr(self.panel, 'dump_memory') and callable(self.panel.dump_memory):
                    logger.warn("Requested memory dump. Dumping...")

                    await self.panel.dump_memory()
                    logger.warn("Memory dump completed. Exiting pai.")
                    raise SystemExit()
                else:
                    logger.warn("Requested memory dump, but current panel type does not support it yet.")

            await self.panel.update_labels()


            logger.info("Connection OK")
            self.loop_wait = False

            ps.sendMessage('connected')
            return True
        except ConnectionError as e:
            logger.error("Failed to connect: %s" % str(e))
        except Exception:
            logger.exception("Connect error")

        self.run = STATE_STOP
        return False

    async def sync_time(self):
        logger.debug("Synchronizing panel time")

        now = time.localtime()
        args = dict(century=int(now.tm_year / 100), year=int(now.tm_year % 100),
                    month=now.tm_mon, day=now.tm_mday, hour=now.tm_hour, minute=now.tm_min)

        reply = await self.send_wait(self.panel.get_message('SetTimeDate'), args, reply_expected=0x03, timeout=10)
        if reply is None:
            logger.warn("Could not set panel time")
        else:
            logger.info("Panel time synchronized")

    def loop(self):
        task = self.work_loop.create_task(self.async_loop())
        self.work_loop.run_until_complete(task)

    async def async_loop(self):
        logger.debug("Loop start")

        while self.run != STATE_STOP:

            while self.run == STATE_PAUSE:
                await asyncio.sleep(5)

            # May happen when out of sleep
            if self.run == STATE_STOP:
                break

            self.loop_wait = True

            tstart = time.time()
            try:
                for i in cfg.STATUS_REQUESTS:
                    logger.debug("Requesting status: %d" % i)
                    reply = await self.panel.request_status(i)
                    if reply is not None:
                        tstart = time.time()
                        self.panel.handle_status(reply)
                    else:
                        logger.error("No reply to status request: %d" % i)
            except ConnectionError:
                raise
            except Exception:
                logger.exception("Loop")

            # cfg.Listen for events
            while time.time() - tstart < cfg.KEEP_ALIVE_INTERVAL and self.run == STATE_RUN and self.loop_wait:
                await asyncio.sleep(min(time.time() - tstart, 1))

    async def receive_worker(self):
        logger.debug("Receive worker started")
        async_supported = asyncio.iscoroutinefunction(self.connection.read)
        try:
            while True:
                logger.debug("Receive worker loop")
                if async_supported:
                    await self.receive()
                else:
                    await self.receive()
                    await asyncio.sleep(0.1)  # we need this until we use fully async receive. This lets other loop events to continue their work
        except asyncio.CancelledError:
            logger.debug("Receive worker canceled")

        logger.debug("Receive worker stopped")

    async def receive(self, timeout=5.0):
        # TODO: Get rid of receive worker
        # with serial_lock:
        
        data = self.connection.read(timeout=timeout)
        if isinstance(data, Awaitable):
            try:
                data = await data
            except asyncio.TimeoutError:
                return None

        # Retry if no data was available
        if data is None or len(data) == 0:
            return None

        self.message_manager.schedule_raw_message_handling(data)


        try:
            recv_message = self.panel.parse_message(data, direction='frompanel')

            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug(recv_message)

            # No message
            if recv_message is None:
                logger.debug("Unknown message: %s" % (" ".join("{:02x} ".format(c) for c in data)))
                return None

            if self.run != STATE_PAUSE:
                self.message_manager.schedule_message_handling(recv_message)  # schedule handling in the loop
        except Exception:
            logging.exception("Error parsing message")
            return None

    def send_wait_simple(self, message=None, timeout=5.0, wait=True) -> Optional[bytes]:
        # Connection closed
        if not self.connection.connected:
            raise ConnectionError('Not connected')

        with serial_lock:
            if message is not None:
                self.connection.timeout(timeout)
                self.connection.write(message)

            if not wait:
                return None
            
            data = self.connection.read(timeout=timeout)
            
            if isinstance(data, Awaitable):
                future = asyncio.run_coroutine_threadsafe(data, self.work_loop)
                try:
                    data = future.result(5)
                except asyncio.TimeoutError:
                    data = None

        return data

    async def send_wait(self,
                  message_type=None,
                  args=None,
                  message=None,
                  retries=5,
                  timeout=0.5,
                  reply_expected=None) -> Optional[Container]:

        # Connection closed
        if not self.connection.connected:
            raise ConnectionError('Not connected')

        if message is None and message_type is not None:
            message = message_type.build(dict(fields=dict(value=args)))

        while retries >= 0:
            retries -= 1

            with serial_lock:
                if message is not None:
                    self.connection.timeout(timeout)
                    self.connection.write(message)

            if reply_expected is not None:
                self.work_loop.create_task(self.receive(timeout))
                if isinstance(reply_expected, Callable):
                    reply = await self.message_manager.wait_for(reply_expected, timeout=timeout*2)
                elif isinstance(reply_expected, Iterable):
                    reply = await self.message_manager.wait_for(
                        lambda m: any(m.fields.value.po.command == expected for expected in reply_expected), timeout=timeout*2)
                else:
                    reply = await self.message_manager.wait_for(lambda m: m.fields.value.po.command == reply_expected, timeout=timeout*2)

                if reply:
                    return reply

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

    def control_zone(self, zone: str, command: str) -> bool:
        logger.debug("Control Zone: {} - {}".format(zone, command))

        zones_selected = self._select(self.data['zone'], zone)  # type: Sequence[int]

        # Not Found
        if len(zones_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        try:
            coro = self.panel.control_zones(zones_selected, command)
            future = asyncio.run_coroutine_threadsafe(coro, self.work_loop)
            accepted = future.result(10)
        except NotImplementedError:
            logger.error('control_zones is not implemented for this alarm type')
        except asyncio.TimeoutError:
            logger.error('control_zones timeout')
            future.cancel()

        # Refresh status
        self.loop_wait = False

        return accepted

    def control_partition(self, partition: str, command: str) -> bool:
        logger.debug("Control Partition: {} - {}".format(partition, command))

        partitions_selected = self._select(self.data['partition'], partition)  # type: Sequence[int]

        # Not Found
        if len(partitions_selected) == 0:
            return False

        # Apply state changes
        accepted = False
        try:
            coro = self.panel.control_partitions(partitions_selected, command)
            future = asyncio.run_coroutine_threadsafe(coro, self.work_loop)
            accepted = future.result(10)
        except NotImplementedError:
            logger.error('control_partitions is not implemented for this alarm type')
        except asyncio.TimeoutError:
            logger.error('control_partitions timeout')
            future.cancel()

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
            coro = self.panel.control_outputs(outputs_selected, command)
            future = asyncio.run_coroutine_threadsafe(coro, self.work_loop)
            accepted = future.result(10)
        except NotImplementedError:
            logger.error('control_outputs is not implemented for this alarm type')
        except asyncio.TimeoutError:
            logger.error('control_outputs timeout')
            future.cancel()
        # Apply state changes

        # Refresh status
        self.loop_wait = False

        return accepted

    def get_label(self, label_type: str, label_id):
        if label_type in self.data:
            el = self.data[label_type].get(label_id)
            if el:
                return el.get("label")

    def handle_event(self, message: Container):
        """Process cfg.Live Event Message and dispatch it to the interface module"""
        try:
            evt = event.Event(self.panel.event_map, message, label_provider=self.get_label)

            logger.debug("Handle Event: {}".format(evt))

            # Temporary to catch labels/properties in wrong places
            # TODO: REMOVE
            if evt.type in self.data:
                if not evt.id:
                    logger.warn("Missing element ID in {}/{}, m/m: {}/{}, message: {}".format(evt.type, evt.label or '?', evt.major, evt.minor, evt.message))
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
        except Exception as e:
            logger.exception("Handle event")

    def update_properties(self, element_type: str, type_key: str, change: dict,
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
                        if notify != NotifyPropertyChange.NO and (
                                (element_type == "partition"
                                 and ('partition' not in cfg.LIMITS or type_key in cfg.LIMITS['partition'])
                                 and property_name not in cfg.PARTITIONS_CHANGE_NOTIFICATION_IGNORE
                                )
                                or ('trouble' in property_name)
                        ):
                            self.interface.notify("Paradox", "{} {} {}".format(elements[type_key]['key'],
                                                                               property_name,
                                                                               property_value), logging.INFO)
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

        if error_enum == 'panel_not_connected':
            self.disconnect()
        else:
            message = self.panel.get_error_message(error_enum)
            logger.error("Got ERROR Message: {}".format(message))

    def disconnect(self):
        logger.info("Disconnecting from the Alarm Panel")
        self.run = STATE_STOP
        self.loop_wait = False

        self.clean_session()
        if self.connection.connected:
            self.connection.close()
            logger.info("Disconnected from the Alarm Panel")

    async def pause(self):
        logger.info("Pausing PAI")
        if self.run == STATE_RUN:
            logger.info("Pausing from the Alarm Panel")
            self.run = STATE_PAUSE
            self.loop_wait = False
            # EVO IP150 IP Interface does not work if we send this
            # await self.send_wait(self.panel.get_message('CloseConnection'), None)

    async def resume(self):
        logger.info("Resuming PAI")
        if self.run == STATE_PAUSE:
            await self.connect_async()

    def clean_session(self):
        logger.info("Clean Session")
        if self.connection.connected:
            if not self.panel:
                panel = create_panel(self)
            else:
                panel = self.panel

            logger.info("Cleaning previous session. Closing connection")
            # Write directly as this can be called from other contexts

            self.connection.write(panel.get_message('CloseConnection').build(dict()))
