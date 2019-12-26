# -*- coding: utf-8 -*-

import asyncio
import logging
import time
from binascii import hexlify
from enum import Enum
from threading import Lock
from typing import Optional, Sequence, Iterable, Callable

from construct import Container

from paradox.event import Event, LiveEvent, ChangeEvent, Change
from paradox.config import config as cfg
from paradox.connections.ip_connection import IPConnection
from paradox.connections.serial_connection import SerialCommunication
from paradox.data.memory_storage import MemoryStorage as Storage
from paradox.exceptions import StatusRequestException
from paradox.hardware import create_panel
from paradox.lib import ps
from paradox.lib.async_message_manager import EventMessageHandler, ErrorMessageHandler
from paradox.lib.utils import deep_merge
from paradox.parsers.status import convert_raw_status

logger = logging.getLogger('PAI').getChild(__name__)

serial_lock = Lock()


class State(Enum):
    STOP = 0
    INIT = 1
    RUN = 2
    PAUSE = 3
    ERROR = 4


def async_loop_unhandled_exception_handler(loop, context):
    logger.error("Unhandled exception in async loop(%s): %s", loop, context)

    loop.default_exception_handler(context)
    # exception = context.get('exception')
    logger.exception("Unhandled exception in async loop")

class Paradox:
    def __init__(self, retries=3):
        self.panel = None  # type: Panel
        self._connection = None
        self.retries = retries
        self.work_loop = asyncio.get_event_loop() # type: asyncio.AbstractEventLoop
        self.work_loop.set_exception_handler(async_loop_unhandled_exception_handler)
        self.receive_worker_task = None

        self.storage = Storage()

        self.run = State.STOP
        self.request_lock = asyncio.Lock()
        self.loop_wait_event = asyncio.Event()

        ps.subscribe(self._on_labels_load, "labels_loaded")
        ps.subscribe(self._on_definitions_load, "definitons_loaded")
        ps.subscribe(self._on_status_update, "status_update")
        ps.subscribe(self._on_event, "events")
        ps.subscribe(self._on_property_change, "changes")

    @property
    def connection(self):
        if not self._connection:
            # Load a connection to the alarm
            if cfg.CONNECTION_TYPE == "Serial":
                logger.info("Using Serial Connection")

                self._connection = SerialCommunication(self.on_connection_message, port=cfg.SERIAL_PORT,
                                                      baud=cfg.SERIAL_BAUD)
            elif cfg.CONNECTION_TYPE == 'IP':
                logger.info("Using IP Connection")

                self._connection = IPConnection(self.on_connection_message, host=cfg.IP_CONNECTION_HOST,
                                               port=cfg.IP_CONNECTION_PORT,
                                               password=cfg.IP_CONNECTION_PASSWORD)
            else:
                raise AssertionError("Invalid connection type: {}".format(cfg.CONNECTION_TYPE))

            self._register_connection_handlers()

        return self._connection

    def _register_connection_handlers(self):
        self.connection.register_handler(EventMessageHandler(self.handle_event_message))
        self.connection.register_handler(ErrorMessageHandler(self.handle_error_message))

    def reset(self):
        pass

    def connect(self) -> bool:
        task = self.work_loop.create_task(self.connect_async())
        self.work_loop.run_until_complete(task)
        return task.result()

    async def connect_async(self):
        self.disconnect()  # socket needs to be also closed
        self.panel = None

        logger.info("Connecting to interface")
        if not await self.connection.connect():
            logger.error('Failed to connect to interface')
            self.run = State.ERROR
            return False

        logger.info("Connecting to panel")

        # Reset all states
        self.reset()
        self.run = State.INIT

        if not self.panel:
            self.panel = create_panel(self)
            self.connection.variable_message_length(self.panel.variable_message_length)

        try:
            logger.info("Initiating communication")

            initiate_reply = await self.send_wait(self.panel.get_message('InitiateCommunication'), None, reply_expected=0x07)

            if initiate_reply:
                model = initiate_reply.fields.value.label.strip(b'\0 ').decode(cfg.LABEL_ENCODING)
                firmware_version = "{}.{} build {}".format(
                    initiate_reply.fields.value.application.version,
                    initiate_reply.fields.value.application.revision,
                    initiate_reply.fields.value.application.build
                )
                serial_number = hexlify(initiate_reply.fields.value.serial_number).decode()

                logger.info("Found Panel {} version {}".format(model, firmware_version))
            else:
                raise ConnectionError("Panel did not replied to InitiateCommunication")


            logger.info("Starting communication")
            reply = await self.send_wait(self.panel.get_message('StartCommunication'),
                                         args=dict(source_id=0x02), reply_expected=0x00)

            if reply is None:
                raise ConnectionError("Panel did not replied to StartCommunication")

            if reply.fields.value.product_id is not None:
                self.panel = create_panel(self, reply.fields.value.product_id)  # Now we know what panel it is. Let's
                # recreate panel object.
                ps.sendMessage('panel_detected', panel=dict(product_id=reply.fields.value.product_id, model=model, firmware_version=firmware_version, serial_number=serial_number))

            result = await self.panel.initialize_communication(reply, cfg.PASSWORD)
            if not result:
                raise ConnectionError("Failed to initialize communication")

            if cfg.SYNC_TIME:
                await self.sync_time()

            if cfg.DEVELOPMENT_DUMP_MEMORY:
                if hasattr(self.panel, 'dump_memory') and callable(self.panel.dump_memory):
                    logger.warning("Requested memory dump. Dumping...")

                    await self.panel.dump_memory()
                    logger.warning("Memory dump completed. Exiting pai.")
                    raise SystemExit()
                else:
                    logger.warning("Requested memory dump, but current panel type does not support it yet.")

            logger.info("Loading definitions")
            definitions = await self.panel.load_definitions()
            ps.sendMessage('definitions_loaded', data=definitions)

            logger.info("Loading labels")
            labels = await self.panel.load_labels()
            ps.sendMessage('labels_loaded', data=labels)

            logger.info("Connection OK")
            self.run = State.RUN
            self.request_status_refresh()  # Trigger status update

            ps.sendMessage('connected')
            return True
        except asyncio.TimeoutError as e:
            logger.error("Timeout while connecting to panel: %s" % str(e))
        except ConnectionError as e:
            logger.error("Failed to connect: %s" % str(e))
        except Exception:
            logger.exception("Connect error")

        self.run = State.ERROR

        return False

    async def sync_time(self):
        logger.debug("Synchronizing panel time")

        now = time.localtime()
        args = dict(century=int(now.tm_year / 100), year=int(now.tm_year % 100),
                    month=now.tm_mon, day=now.tm_mday, hour=now.tm_hour, minute=now.tm_min)

        reply = await self.send_wait(self.panel.get_message('SetTimeDate'), args, reply_expected=0x03, timeout=10)
        if reply is None:
            logger.warning("Could not set panel time")
        else:
            logger.info("Panel time synchronized")

    def loop(self):
        task = self.work_loop.create_task(self.async_loop())
        self.work_loop.run_until_complete(task)

    async def async_loop(self):
        logger.debug("Loop start")
        
        replies_missing = 0

        while self.run not in(State.STOP, State.ERROR):
            tstart = time.time()
            if self.run == State.RUN:
                try:
                    result = await asyncio.gather(*[self._status_request(i) for i in cfg.STATUS_REQUESTS])
                    merged = deep_merge(*result, extend_lists=True, initializer={})
                    self.work_loop.call_soon(self._process_status, merged)
                    replies_missing = max(0, replies_missing - 1)
                except ConnectionError:
                    raise
                except StatusRequestException:
                    replies_missing += 1
                    if replies_missing > 3:
                        logger.error("Lost communication with panel")
                        self.disconnect()
                except Exception:
                    logger.exception("Loop")

                if replies_missing > 0:
                    logger.debug("Loop: Replies missing: {}".format(replies_missing))

            # cfg.Listen for events

            max_wait_time = max((tstart + cfg.KEEP_ALIVE_INTERVAL) - time.time(), 0)
            try:
                await asyncio.wait_for(self.loop_wait_event.wait(), max_wait_time)
            except asyncio.TimeoutError:
                # It is fine to timeout to go to the next loop
                pass
            finally:
                self.loop_wait_event.clear()

    async def _status_request(self, i):
        logger.debug("Scheduling status request: %d" % i)
        return await self.panel.request_status(i)

    @staticmethod
    def _process_status(raw_status: Container):
        status = convert_raw_status(raw_status)

        for limit_key, limit_arr in cfg.LIMITS.items():
            if limit_key not in status:
                continue

            status[limit_key].filter(limit_arr)

        #     # TODO: throttle power update messages
        #     if time.time() - self.last_power_update >= cfg.POWER_UPDATE_INTERVAL:
        #         force = PublishPropertyChange.YES if cfg.PUSH_POWER_UPDATE_WITHOUT_CHANGE else PublishPropertyChange.NO

        if cfg.LOGGING_DUMP_STATUS:
            logger.debug("properties: %s", status)

        ps.sendMessage('status_update', status=status)

    def request_status_refresh(self):
        self.loop_wait_event.set()

    def on_connection_message(self, message: bytes):
        self.connection.schedule_raw_message_handling(message)

        if not self.panel:
            return
        try:
            recv_message = self.panel.parse_message(message, direction='frompanel')

            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug('Message received: %s', recv_message)

            # No message
            if recv_message is None:
                logger.debug("Unknown message: %s" % (" ".join("{:02x} ".format(c) for c in message)))
                return

            if self.run != State.PAUSE:
                self.connection.schedule_message_handling(recv_message)  # schedule handling in the loop
        except Exception as e:
            logging.exception("Error parsing message")

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

        retry = 0

        while retry <= retries:
            if retry > 0:
                logger.debug('Request retry (%d/%d)', retry, retries)
            retry += 1

            try:
                async with self.request_lock:
                    if message is not None:
                        self.connection.write(message)

                    if reply_expected is not None:
                        if isinstance(reply_expected, Callable):
                            reply = await self.connection.wait_for_message(reply_expected, timeout=timeout * 2)
                        elif isinstance(reply_expected, Iterable):
                            reply = await self.connection.wait_for_message(
                                lambda m: any(m.fields.value.po.command == expected for expected in reply_expected), timeout=timeout*2)
                        else:
                            reply = await self.connection.wait_for_message(lambda m: m.fields.value.po.command == reply_expected, timeout=timeout * 2)

                        if reply:
                            return reply
            except asyncio.TimeoutError:
                pass

        return None  # Probably it needs to throw an exception instead of returning None

    def control_zone(self, zone: str, command: str) -> bool:
        command = command.lower()
        logger.debug("Control Zone: {} - {}".format(zone, command))

        zones_selected = self.storage.get_container('zone').select(zone)  # type: Sequence[int]

        # Not Found
        if len(zones_selected) == 0:
            logger.error('No zones selected')
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
        self.request_status_refresh()  # Trigger status update

        return accepted

    def control_partition(self, partition: str, command: str) -> bool:
        command = command.lower()
        logger.debug("Control Partition: {} - {}".format(partition, command))

        partitions_selected = self.storage.get_container('partition').select(partition) # type: Sequence[int]

        # Not Found
        if len(partitions_selected) == 0:
            logger.error('No partitions selected')
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

        # Refresh status
        self.request_status_refresh()  # Trigger status update

        return accepted

    def control_output(self, output, command) -> bool:
        command = command.lower()
        logger.debug("Control Output: {} - {}".format(output, command))

        outputs_selected = self.storage.get_container('pgm').select(output)

        # Not Found
        if len(outputs_selected) == 0:
            logger.error('No outputs selected')
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
        self.request_status_refresh()  # Trigger status update

        return accepted

    def get_label(self, label_type: str, label_id) -> Optional[str]:
        el = self.storage.get_container_object(label_type, label_id)
        if el:
            return el.get("label")

    def handle_event_message(self, message: Container=None):
        """Process cfg.Live Event Message and dispatch it to the interface module"""
        try:
            try:
                evt = LiveEvent(event=message, event_map=self.panel.event_map, label_provider=self.get_label)
            except AssertionError as e:
                logger.debug("Error creating event")
                return

            element = self.storage.get_container_object(evt.type, evt.id)

            # Temporary to catch labels/properties in wrong places
            # TODO: REMOVE
            if message is not None:
                if not evt.id:
                    logger.warning("Missing element ID in {}/{}, m/m: {}/{}, message: {}".format(evt.type, evt.label or '?', evt.major, evt.minor, evt.message))
                else:
                    if not element:
                        logger.warning("Missing element with ID {} in {}/{}".format(evt.id, evt.type, evt.label))
                    else:
                        for k in evt.change:
                            if k not in element:
                                logger.warning("Missing property {} in {}/{}".format(k, evt.type, evt.label))
                        if evt.label != element.get("label"):
                            logger.warning(
                                "Labels differ {} != {} in {}/{}".format(element.get("label"), evt.label, evt.type, evt.label))
            # Temporary end
            
            # The event has changes. Update the state
            if len(evt.change) > 0 and element:
                self.storage.update_container_object(evt.type, evt.id, evt.change)

            ps.sendEvent(evt)

        except Exception as e:
            logger.exception("Handle live event")

    def handle_error_message(self, message):
        """Handle ErrorMessage"""
        error_enum = message.fields.value.message

        if error_enum == 'panel_not_connected':
            self.disconnect()
        else:
            message = self.panel.get_error_message(error_enum)
            logger.error("Got ERROR Message: {}".format(message))

    def disconnect(self):
        logger.info("Disconnecting from the Alarm Panel")
        self.run = State.STOP

        self._clean_session()
        if self.connection.connected:
            self.connection.close()
            logger.info("Disconnected from the Alarm Panel")

    async def pause(self):
        logger.info("Pausing PAI")
        if self.run == State.RUN:
            logger.info("Pausing from the Alarm Panel")
            self.run = State.PAUSE
            # EVO IP150 IP Interface does not work if we send this
            # await self.send_wait(self.panel.get_message('CloseConnection'), None)

    async def resume(self):
        logger.info("Resuming PAI")
        if self.run == State.PAUSE:
            await self.connect_async()

    def _clean_session(self):
        logger.info("Clean Session")
        if self.connection.connected:
            if not self.panel:
                panel = create_panel(self)
            else:
                panel = self.panel

            logger.info("Cleaning previous session. Closing connection")
            # Write directly as this can be called from other contexts

            self.connection.write(panel.get_message('CloseConnection').build(dict()))

    def _on_labels_load(self, data):
        for k, d in data.items():
            self.storage.get_container(k).deep_merge(d)

    def _on_definitions_load(self, data):
        for k, d in data.items():
            self.storage.get_container(k).deep_merge(d)

    def _on_status_update(self, status):
        """
        Calls update_properties
        :param status:
        :return:
        """
        if 'troubles' in status:
            self._process_trouble_statuses(status['troubles'])

        for element_type, element_items in status.items():
            if element_type in ['troubles']:  # troubles was already parsed
                continue
            for element_item_key, element_item_status in element_items.items():
                if isinstance(element_item_status, (dict, list,)):
                    self.storage.update_container_object(element_type, element_item_key, element_item_status)
                else:
                    logger.debug("%s/%s:%s ignored", element_type, element_item_key, element_item_status)

        self._update_partition_states()

    def _process_trouble_statuses(self, trouble_statuses):
        global_trouble = False
        for t_key, t_status in trouble_statuses.items():
            if not isinstance(t_status, bool):
                logger.error("Trouble %s has not boolean state: %s", t_key, t_status)
                continue

            self.storage.update_container_object('system', 'troubles', {t_key: t_status})

            global_trouble = global_trouble or t_status

        self.storage.update_container_object('system', 'troubles', {'trouble': global_trouble})

    def _update_partition_states(self):
        """
        current_state is fully HomeAssistant compatible. Check HASS manual before making any changes.
        """
        for _, properties in self.storage.get_container('partition').items():
            change = {}
            if any([
                properties.get('fire_alarm'),
                properties.get('audible_alarm'),
                properties.get('silent_alarm'),
                properties.get('panic_alarm')
            ]):
                change["current_state"] = 'triggered'
            elif properties.get('arm'):
                if properties.get('arm_stay'):
                    change["current_state"] = 'armed_home'
                elif properties.get('arm_sleep'):
                    change["current_state"] = 'armed_night'
                elif properties.get('arm_away'):
                    change["current_state"] = 'armed_away'
                else:
                    change["current_state"] = 'armed_away'

                change["target_state"] = change["current_state"]
            else:
                change["target_state"] = change["current_state"] = 'disarmed'

            if properties.get('exit_delay'):  # Redefine if pending
                change["current_state"] = 'pending'

            self.storage.update_container_object('partition', properties['key'], change)

    def _on_event(self, event: Event):
        if cfg.LOGGING_DUMP_EVENTS:
            logger.debug("LiveEvent: {}".format(event))

        event.call_hook(storage=self.storage, alarm=self)

        if isinstance(event, LiveEvent):
            self._update_partition_states()

    def _on_property_change(self, change: Change):
        if change.initial:
            return

        try:
            event = ChangeEvent(change_object=change, property_map=self.panel.property_map, label_provider=self.get_label)
            if cfg.LOGGING_DUMP_EVENTS:
                logger.debug("ChangeEvent: {}".format(event))
            ps.sendEvent(event)
        except AssertionError:
            logger.debug("Could not create event from change")