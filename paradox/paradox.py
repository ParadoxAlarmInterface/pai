import asyncio
from binascii import hexlify
from datetime import datetime
import logging
import time
from typing import Callable, Iterable, Optional

from construct import Container
import pytz

from paradox.config import config as cfg, get_limits_for_type
from paradox.connections.connection import Connection
from paradox.data.enums import RunState
from paradox.data.memory_storage import MemoryStorage as Storage
from paradox.data.model import DetectedPanel
from paradox.event import Change, ChangeEvent, Event, LiveEvent
from paradox.exceptions import (
    AuthenticationFailed,
    CodeLockout,
    PanelNotDetected,
    StatusRequestException,
    async_loop_unhandled_exception_handler,
)
from paradox.hardware import Panel, create_panel
from paradox.lib import ps
from paradox.lib.async_message_manager import ErrorMessageHandler, EventMessageHandler
from paradox.lib.handlers import PersistentHandler
from paradox.lib.utils import deep_merge
from paradox.parsers.status import convert_raw_status

logger = logging.getLogger("PAI").getChild(__name__)


class Paradox:
    def __init__(self, retries=3):
        self.panel: Panel = None
        self._connection: Connection = None
        self.retries = retries
        self.work_loop = asyncio.get_event_loop()
        self.work_loop.set_exception_handler(async_loop_unhandled_exception_handler)

        self.storage = Storage()

        self._run_state = RunState.STOP
        self.request_lock = asyncio.Lock()
        self.busy = asyncio.Lock()
        self.loop_wait_event = asyncio.Event()

        ps.subscribe(self._on_labels_load, "labels_loaded")
        ps.subscribe(self._on_definitions_load, "definitons_loaded")
        ps.subscribe(self._on_status_update, "status_update")
        ps.subscribe(self._on_event, "events")
        ps.subscribe(self._on_property_change, "changes")

    @property
    def run_state(self) -> RunState:
        return self._run_state

    @run_state.setter
    def run_state(self, value: RunState):
        self._run_state = value
        ps.sendMessage("run-state", state=value)

    @property
    def connection(self):
        if not self._connection:
            # Load a connection to the alarm
            if cfg.CONNECTION_TYPE == "Serial":
                logger.info("Using Serial Connection")

                from paradox.connections.serial_connection import SerialCommunication

                self._connection = SerialCommunication(
                    port=cfg.SERIAL_PORT,
                    baud=cfg.SERIAL_BAUD,
                )
            elif cfg.CONNECTION_TYPE == "IP":
                logger.info("Using IP Connection")

                if cfg.IP_CONNECTION_BARE:
                    from paradox.connections.ip.connection import BareIPConnection

                    self._connection = BareIPConnection(
                        host=cfg.IP_CONNECTION_HOST, port=cfg.IP_CONNECTION_PORT
                    )
                elif cfg.IP_CONNECTION_SITEID and cfg.IP_CONNECTION_EMAIL:
                    from paradox.connections.ip.connection import StunIPConnection

                    self._connection = StunIPConnection(
                        site_id=cfg.IP_CONNECTION_SITEID,
                        email=cfg.IP_CONNECTION_EMAIL,
                        panel_serial=cfg.IP_CONNECTION_PANEL_SERIAL,
                        password=cfg.IP_CONNECTION_PASSWORD,
                    )
                else:
                    from paradox.connections.ip.connection import LocalIPConnection

                    self._connection = LocalIPConnection(
                        host=cfg.IP_CONNECTION_HOST,
                        port=cfg.IP_CONNECTION_PORT,
                        password=cfg.IP_CONNECTION_PASSWORD,
                    )
            else:
                raise AssertionError(f"Invalid connection type: {cfg.CONNECTION_TYPE}")

            self._register_connection_handlers()

        return self._connection

    def _register_connection_handlers(self):
        self.connection.register_raw_handler(
            PersistentHandler(self.on_connection_message)
        )

        self.connection.register_handler(EventMessageHandler(self.handle_event_message))
        self.connection.register_handler(ErrorMessageHandler(self.handle_error_message))

    async def connect(self) -> bool:
        if self._connection:
            await self.disconnect()  # socket needs to be also closed
        self.panel = None

        self.run_state = RunState.INIT
        logger.info("Connecting to interface")
        if not await self.connection.connect():
            self.run_state = RunState.ERROR
            logger.error("Failed to connect to interface")
            return False

        logger.info("Connecting to Panel")

        if not self.panel:
            self.panel = create_panel(self)
            self.connection.variable_message_length(self.panel.variable_message_length)

        try:
            initiate_reply = await self.send_wait(
                self.panel.get_message("InitiateCommunication"),
                None,
                reply_expected=0x7,
            )

            if initiate_reply:
                model = initiate_reply.fields.value.label.strip(b"\0 ").decode(
                    cfg.LABEL_ENCODING
                )
                firmware_version = "{}.{} build {}".format(
                    initiate_reply.fields.value.application.version,
                    initiate_reply.fields.value.application.revision,
                    initiate_reply.fields.value.application.build,
                )
                serial_number = hexlify(
                    initiate_reply.fields.value.serial_number
                ).decode()

                logger.info(f"Panel Identified {model} version {firmware_version}")
            else:
                raise ConnectionError("Panel did not replied to InitiateCommunication")

            logger.info("Initiating panel connection")
            reply = await self.send_wait(
                self.panel.get_message("StartCommunication"),
                args=dict(source_id=0x2),
                reply_expected=0x0,
            )

            if reply is None:
                raise ConnectionError("Panel did not replied to StartCommunication")

            if reply.fields.value.product_id is not None:
                self.panel = create_panel(
                    self, reply
                )  # Now we know what panel it is. Let's
                # recreate panel object.
                ps.sendMessage(
                    "panel_detected",
                    panel=DetectedPanel(
                        product_id=reply.fields.value.product_id,
                        model=model,
                        firmware_version=firmware_version,
                        serial_number=serial_number,
                    ),
                )
            else:
                raise PanelNotDetected("Failed to detect panel")

            result = await self.panel.initialize_communication(cfg.PASSWORD)
            if not result:
                raise ConnectionError("Failed to initialize communication")

            self.run_state = RunState.CONNECTED
            logger.info("Connection OK")
            return True
        except asyncio.TimeoutError:
            logger.error(
                "Timeout while connecting to panel. Is an other connection active?"
            )
        except ConnectionError as e:
            logger.error("Failed to connect: %s" % str(e))

        self.run_state = RunState.ERROR

        return False

    async def full_connect(self) -> bool:
        try:
            if not await self.connect():
                return False

            logger.info("Loading data from panel memory")
            await self.panel.load_memory()

            logger.info("Running")
            self.run_state = RunState.RUN
            self.request_status_refresh()  # Trigger status update

            ps.sendMessage("connected")
            return True
        except asyncio.TimeoutError:
            logger.error(
                "Timeout while connecting to panel. Is an other connection active?"
            )
        except ConnectionError as e:
            logger.error("Failed to connect: %s" % str(e))

        self.run_state = RunState.ERROR

        return False

    async def dump_memory(self, file, memory_type):
        if hasattr(self.panel, "dump_memory") and callable(self.panel.dump_memory):
            logger.warning("Requested memory dump. Dumping...")

            await self.panel.dump_memory(file, memory_type)
            logger.warning("Memory dump completed. Exiting pai.")
            raise SystemExit()
        else:
            logger.warning(
                "Requested memory dump, but current panel type does not support it yet."
            )

    async def sync_time(self):
        now = datetime.now().astimezone()
        if cfg.SYNC_TIME_TIMEZONE:
            try:
                tzinfo = pytz.timezone(cfg.SYNC_TIME_TIMEZONE)
                now = now.astimezone(tzinfo)
            except pytz.exceptions.UnknownTimeZoneError:
                logger.debug(
                    f"Panel Timezone Unknown ('{cfg.SYNC_TIME_TIMEZONE}'). Skipping sync"
                )
                return

        if not self._is_time_sync_required(now.replace(tzinfo=None)):
            return

        args = dict(
            century=int(now.year / 100),
            year=int(now.year % 100),
            month=now.month,
            day=now.day,
            hour=now.hour,
            minute=now.minute,
        )

        logger.debug("Synchronizing panel time")
        reply = await self.send_wait(
            self.panel.get_message("SetTimeDate"), args, reply_expected=0x3, timeout=10
        )
        if reply is None:
            logger.warning("Could not set panel time")
        else:
            logger.info("Panel time synchronized")

    async def loop(self):
        logger.debug("Loop start")

        replies_missing = 0

        while self.run_state not in (RunState.STOP, RunState.ERROR):
            tstart = time.time()
            if self.run_state == RunState.RUN:
                try:
                    await self.busy.acquire()
                    result = await asyncio.gather(*self.panel.get_status_requests())
                    merged = deep_merge(*result, extend_lists=True, initializer={})
                    self.work_loop.call_soon(self._process_status, merged)
                    replies_missing = max(0, replies_missing - 1)
                except ConnectionError:
                    raise
                except (StatusRequestException, asyncio.TimeoutError):
                    replies_missing += 1
                    if replies_missing > 3:
                        logger.error("Lost communication with panel")
                        await self.disconnect()
                        return
                except Exception:
                    logger.exception("Loop")
                finally:
                    self.busy.release()

                if replies_missing > 0:
                    logger.debug(f"Loop: Replies missing: {replies_missing}")

            # cfg.Listen for events

            max_wait_time = max((tstart + cfg.KEEP_ALIVE_INTERVAL) - time.time(), 0)
            try:
                await asyncio.wait_for(self.loop_wait_event.wait(), max_wait_time)
            except asyncio.TimeoutError:
                # It is fine to timeout to go to the next loop
                pass
            finally:
                self.loop_wait_event.clear()

    @staticmethod
    def _process_status(raw_status: Container) -> None:
        status = convert_raw_status(raw_status)

        for limit_key in cfg.LIMITS.keys():
            if limit_key not in status:
                continue

            limit_arr = get_limits_for_type(limit_key)
            if limit_arr is not None:
                status[limit_key].filter(limit_arr)

        if cfg.LOGGING_DUMP_STATUS:
            logger.debug("properties: %s", status)

        ps.sendMessage("status_update", status=status)

    def request_status_refresh(self):
        self.loop_wait_event.set()

    def on_connection_message(self, message: bytes):
        if not self.panel:
            return

        try:
            recv_message = self.panel.parse_message(message, direction="frompanel")

            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug("Message received: %s", recv_message)

            # No message
            if recv_message is None:
                logger.debug(
                    "Unknown message: %s" % (" ".join(f"{c:02x} " for c in message))
                )
                return

            self.connection.schedule_message_handling(
                recv_message
            )  # schedule handling in the loop
        except Exception:
            logger.exception("Error parsing message")

    async def send_wait(
        self,
        message_type=None,
        args=None,
        message=None,
        retries=5,
        timeout=cfg.IO_TIMEOUT,
        reply_expected=None,
    ) -> Optional[Container]:
        # Connection closed
        if not self.connection.connected:
            raise ConnectionError("Not connected")

        if message is None and message_type is not None:
            message = message_type.build(dict(fields=dict(value=args)))

        attempt = 1

        while attempt <= retries:
            if attempt >= 2:  # second and further attempts
                logger.debug("Request retry (attempt %d/%d)", attempt, retries)

            async with self.request_lock:
                t1 = time.time()
                result = "unknown"
                try:
                    if message is not None:
                        self.connection.write(message)

                    if reply_expected is not None:
                        if isinstance(reply_expected, Callable):
                            reply = await self.connection.wait_for_message(
                                reply_expected, timeout=timeout * 2
                            )
                        elif isinstance(reply_expected, Iterable):
                            reply = await self.connection.wait_for_message(
                                lambda m: any(
                                    m.fields.value.po.command == expected
                                    for expected in reply_expected
                                ),
                                timeout=timeout * 2,
                            )
                        else:
                            reply = await self.connection.wait_for_message(
                                lambda m: m.fields.value.po.command == reply_expected,
                                timeout=timeout * 2,
                            )

                        result = "ok"
                        return reply
                except asyncio.TimeoutError:
                    result = "timeout"
                    if attempt == retries:
                        raise
                except ConnectionError:
                    result = "connection error"
                    raise
                except Exception:
                    result = "exception"
                    logger.exception("Unexpected exception during send_wait")
                    raise
                finally:
                    logger.debug("send/receive %s in %.4f s", result, time.time() - t1)

            attempt += 1

        return None  # Probably it needs to throw an exception instead of returning None

    async def control_zone(self, zone: str, command: str) -> bool:
        command = command.lower()
        logger.debug(f"Control Zone: {zone} - {command}")

        zones_selected = self.storage.get_container("zone").select(zone)

        # Not Found
        if len(zones_selected) == 0:
            logger.error("No zones selected")
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = await self.panel.control_zones(zones_selected, command)
        except NotImplementedError:
            logger.error("control_zone is not implemented for this alarm type")
        except asyncio.CancelledError:
            logger.error("control_zone canceled")
        except asyncio.TimeoutError:
            logger.error("control_zone timeout")

        # Refresh status
        self.request_status_refresh()  # Trigger status update

        return accepted

    async def control_partition(self, partition: str, command: str) -> bool:
        command = command.lower()
        logger.debug(f"Control Partition: {partition} - {command}")

        partitions_selected = self.storage.get_container("partition").select(partition)

        # Not Found
        if len(partitions_selected) == 0:
            logger.error("No partitions selected")
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = await self.panel.control_partitions(partitions_selected, command)
        except NotImplementedError:
            logger.error("control_partition is not implemented for this alarm type")
        except asyncio.CancelledError:
            logger.error("control_partition canceled")
        except asyncio.TimeoutError:
            logger.error("control_partition timeout")

        # Refresh status
        self.request_status_refresh()  # Trigger status update

        return accepted

    async def control_output(self, output, command) -> bool:
        command = command.lower()
        logger.debug(f"Control Output: {output} - {command}")

        outputs_selected = self.storage.get_container("pgm").select(output)

        # Not Found
        if len(outputs_selected) == 0:
            logger.error("No outputs selected")
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = await self.panel.control_outputs(outputs_selected, command)
        except NotImplementedError:
            logger.error("control_output is not implemented for this alarm type")
        except asyncio.CancelledError:
            logger.error("control_output canceled")
        except asyncio.TimeoutError:
            logger.error("control_output timeout")
        # Apply state changes

        # Refresh status
        self.request_status_refresh()  # Trigger status update

        return accepted

    async def send_panic(self, partition_id, panic_type, user_id) -> bool:
        logger.debug(
            "Send panic: {}, user: {}, type: {}".format(
                partition_id, user_id, panic_type
            )
        )

        partition = self.storage.get_container_object("partition", partition_id)
        user = self.storage.get_container_object("user", user_id)

        if partition is None or user is None:
            logger.error("Send panic: user or partition is not found")

        try:
            return await self.panel.send_panic(
                [partition["id"]], panic_type, user["id"]
            )
        except NotImplementedError:
            logger.error("send_panic is not implemented for this alarm type")
        except asyncio.CancelledError:
            logger.error("send_panic canceled")
        except asyncio.TimeoutError:
            logger.error("send_panic timeout")

    async def control_door(self, door, command) -> bool:
        command = command.lower()
        logger.debug(f"Control Door: {door} - {command}")

        doors_selected = self.storage.get_container("door").select(door)

        # Not Found
        if len(doors_selected) == 0:
            logger.error("No doors selected")
            return False

        # Apply state changes
        accepted = False
        try:
            accepted = await self.panel.control_doors(doors_selected, command)
        except NotImplementedError:
            logger.error("control_door is not implemented for this alarm type")
        except asyncio.CancelledError:
            logger.error("control_door canceled")
        except asyncio.TimeoutError:
            logger.error("control_door timeout")
        # Apply state changes

        # Refresh status
        self.request_status_refresh()  # Trigger status update

        return accepted

    def get_label(self, label_type: str, label_id) -> Optional[str]:
        el = self.storage.get_container_object(label_type, label_id)
        if el:
            return el.get("label")

    def handle_event_message(self, message: Container = None):
        """Process cfg.Live Event Message and dispatch it to the interface module"""
        try:
            try:
                evt = LiveEvent(
                    event=message,
                    event_map=self.panel.event_map,
                    label_provider=self.get_label,
                )
            except AssertionError:
                logger.debug("Error creating event")
                return

            element = self.storage.get_container_object(evt.type, evt.id)

            # Temporary to catch labels/properties in wrong places
            # TODO: REMOVE
            if message is not None:
                if not evt.id:
                    logger.debug(
                        "Missing element ID in {}/{}, m/m: {}/{}, message: {}".format(
                            evt.type,
                            evt.label or "?",
                            evt.major,
                            evt.minor,
                            evt.message,
                        )
                    )
                else:
                    if not element:
                        logger.warning(
                            "Missing element with ID {} in {}/{}".format(
                                evt.id, evt.type, evt.label
                            )
                        )
                    else:
                        for k in evt.change:
                            if k not in element:
                                logger.warning(
                                    "Missing property {} in {}/{}".format(
                                        k, evt.type, evt.label
                                    )
                                )
                        if evt.label != element.get("label"):
                            logger.warning(
                                "Labels differ {} != {} in {}/{}".format(
                                    element.get("label"), evt.label, evt.type, evt.label
                                )
                            )
            # Temporary end

            # The event has changes. Update the state
            if len(evt.change) > 0 and element:
                self.storage.update_container_object(evt.type, evt.id, evt.change)

            ps.sendEvent(evt)

        except Exception:
            logger.exception("Handle live event")

    def handle_error_message(self, message):
        """Handle ErrorMessage"""
        error_enum = message.fields.value.message

        if error_enum == "panel_not_connected":
            asyncio.get_event_loop().create_task(self.disconnect())
        else:
            message = self.panel.get_error_message(error_enum)
            logger.error(f"Got ERROR Message: {message}")
            if message == "Invalid PC Password":
                raise AuthenticationFailed()
            elif "code lockout" in message:
                raise CodeLockout()

    async def disconnect(self):
        logger.info("Disconnecting from the Alarm Panel")
        self.run_state = RunState.STOP

        self._clean_session()
        if self.connection.connected:
            await self.connection.close()
            logger.info("Disconnected from the Alarm Panel")

    async def pause(self):
        logger.info("Pausing PAI")
        if self.run_state == RunState.RUN:
            logger.info("Pausing from the Alarm Panel")
            self.run_state = RunState.PAUSE
            self.connection.handler_registry.set_ignore_if_no_handlers(True)
            # EVO IP150 IP Interface does not work if we send this
            # await self.send_wait(self.panel.get_message('CloseConnection'), None)

    async def resume(self):
        logger.info("Resuming PAI")
        if self.run_state == RunState.PAUSE:
            self.connection.handler_registry.set_ignore_if_no_handlers(False)
            await self.full_connect()

    def _clean_session(self):
        logger.info("Clean Session")
        if self.connection.connected:
            if not self.panel:
                logger.info("No panel, creating generic one")
                panel = create_panel(self)
            else:
                panel = self.panel

            logger.info("Cleaning previous session. Closing connection")
            # Write directly as this can be called from other contexts

            self.connection.write(panel.get_message("CloseConnection").build(dict()))

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
        if "troubles" in status:
            self._process_trouble_statuses(status["troubles"])

        for element_type, element_items in status.items():
            if element_type in ["troubles"]:  # troubles was already parsed
                continue
            for element_item_key, element_item_status in element_items.items():
                if isinstance(
                    element_item_status,
                    (
                        dict,
                        list,
                    ),
                ):
                    self.storage.update_container_object(
                        element_type, element_item_key, element_item_status
                    )
                else:
                    logger.debug(
                        "%s/%s:%s ignored",
                        element_type,
                        element_item_key,
                        element_item_status,
                    )

        self._update_partition_states()

        if cfg.SYNC_TIME:
            self.work_loop.create_task(self.sync_time())

    def _process_trouble_statuses(self, trouble_statuses):
        global_trouble = False
        for t_key, t_status in trouble_statuses.items():
            if not isinstance(t_status, bool):
                logger.error("Trouble %s has not boolean state: %s", t_key, t_status)
                continue

            self.storage.update_container_object(
                "system", "troubles", {t_key: t_status}
            )

            global_trouble = global_trouble or t_status

        self.storage.update_container_object(
            "system", "troubles", {"trouble": global_trouble}
        )

    def _is_time_sync_required(self, now) -> bool:
        assert now.tzinfo is None
        try:
            drift = (
                now - self.storage.get_container("system")["date"]["time"]
            ).total_seconds()

            if abs(drift) > cfg.SYNC_TIME_MIN_DRIFT:
                logger.info(f"Time drifted more than allowed: {drift} seconds")
                return True
            else:
                logger.debug(f"Time drifted within allowed range: {drift} seconds")

        except KeyError:
            pass

        return False

    def _update_partition_states(self):
        """
        current_state is fully HomeAssistant compatible. Check HASS manual before making any changes.
        """
        for _, properties in self.storage.get_container("partition").items():
            change = {}
            if any(
                [
                    properties.get("fire_alarm"),
                    properties.get("audible_alarm"),
                    properties.get("silent_alarm"),
                    properties.get("panic_alarm"),
                ]
            ):
                change["current_state"] = "triggered"
            elif properties.get("arm"):
                if properties.get("arm_stay"):
                    change["current_state"] = "armed_home"
                elif properties.get("arm_sleep") or properties.get("arm_no_entry"):
                    change["current_state"] = "armed_night"
                elif properties.get("arm_away"):
                    change["current_state"] = "armed_away"
                else:
                    change["current_state"] = "armed_away"

                change["target_state"] = change["current_state"]
            else:
                change["target_state"] = change["current_state"] = "disarmed"

            if properties.get("exit_delay"):  # Redefine if pending
                change["current_state"] = "arming"

            self.storage.update_container_object("partition", properties["key"], change)

    def _on_event(self, event: Event):
        if cfg.LOGGING_DUMP_EVENTS:
            logger.debug(f"LiveEvent: {event}")

        event.call_hook(storage=self.storage, alarm=self)

        if isinstance(event, LiveEvent):
            self._update_partition_states()

    def _on_property_change(self, change: Change):
        if change.initial:
            return

        try:
            event = ChangeEvent(
                change_object=change,
                property_map=self.panel.property_map,
                label_provider=self.get_label,
            )
            if cfg.LOGGING_DUMP_EVENTS:
                logger.debug(f"ChangeEvent: {event}")
            ps.sendEvent(event)
        except AssertionError:
            logger.debug("Could not create event from change")
