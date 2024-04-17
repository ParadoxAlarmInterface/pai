import asyncio
import binascii
import hashlib
import json
import logging
import os
import typing
from collections import namedtuple

from paho.mqtt.client import Client, MQTTMessage

from paradox.config import config as cfg
from paradox.event import Change, Event, EventLevel, Notification
from paradox.lib import ps
from paradox.lib.utils import (JSONByteEncoder, call_soon_in_main_loop,
                               sanitize_key)

from .core import AbstractMQTTInterface
from .helpers import ELEMENT_TOPIC_MAP, get_control_topic_prefix

logger = logging.getLogger("PAI").getChild(__name__)

ParsedMessage = namedtuple("parsed_message", "topics element content")


def mqtt_handle_decorator(
    func: typing.Callable[
        ["BasicMQTTInterface", ParsedMessage],
        typing.Coroutine[None, "BasicMQTTInterface", ParsedMessage],
    ]
):
    async def try_func(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except:
            logger.exception("Exception executing MQTT function")

    def wrapper(
        self: "BasicMQTTInterface", client: Client, userdata, message: MQTTMessage
    ):
        try:
            if message.retain:
                logger.warning(
                    "Ignoring command: retained message topic={}, payload={}".format(
                        message.topic, str(message.payload.decode("utf-8"))
                    )
                )
                return

            if self.alarm is None:
                logger.warning(
                    "No alarm. Ignoring command: message topic={}, payload={}".format(
                        message.topic, str(message.payload.decode("utf-8"))
                    )
                )
                return

            logger.info(
                "message topic={}, payload={}".format(
                    message.topic, str(message.payload.decode("utf-8"))
                )
            )

            topic = message.topic.split(cfg.MQTT_BASE_TOPIC)[1]

            topics = topic.split("/")

            if len(topics) < 3:
                logger.error("Invalid topic in mqtt message: {}".format(message.topic))
                return

            content = message.payload.decode("utf-8").strip()

            element = None
            if len(topics) >= 4:
                element = topics[3]

            call_soon_in_main_loop(
                try_func(self, ParsedMessage(topics, element, content))
            )
        except:
            logger.exception("Failed to execute command")

    return wrapper


def _extract_command_user(command):
    aux = command.split(" ")
    if len(aux) > 1:
        return aux[0], aux[1]
    else:
        return aux[0], None


class BasicMQTTInterface(AbstractMQTTInterface):
    def __init__(self, alarm):
        super().__init__(alarm)

        self.partitions = {}
        self.definitions = {}
        self.labels = {}
        self.challenges = None
        self.connected_future = (
            asyncio.Future()
        )  # TODO: do not create it, use some other
        self.labels_future = asyncio.Future()
        self.definitions_future = asyncio.Future()

        ready_future = asyncio.ensure_future(
            asyncio.gather(
                self.connected_future, self.labels_future, self.definitions_future
            )
        )
        ready_future.add_done_callback(lambda x: self._on_ready())

        ps.subscribe(self._handle_panel_labels, "labels_loaded")
        ps.subscribe(self._handle_panel_definitions, "definitions_loaded")
        ps.subscribe(self._handle_panel_change, "changes")
        ps.subscribe(self._handle_panel_event, "events")

    def on_connect(self, mqttc, userdata, flags, result):
        self.subscribe_callback(get_control_topic_prefix("output")+"/#",
            self._mqtt_handle_output_control,
        )
        self.subscribe_callback(
            get_control_topic_prefix("door")+"/#",
            self._mqtt_handle_door_control,
        )
        self.subscribe_callback(
            get_control_topic_prefix("zone")+"/#",
            self._mqtt_handle_zone_control,
        )
        self.subscribe_callback(
            get_control_topic_prefix("partition")+"/#",
            self._mqtt_handle_partition_control,
        )
        self.subscribe_callback(
            "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_NOTIFICATIONS_TOPIC, "+"),
            self._mqtt_handle_notifications,
        )
        self.subscribe_callback(
            "{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC, cfg.MQTT_SEND_PANIC_TOPIC, "+", "+"
            ),
            self._mqtt_handle_send_panic,
        )

        if not self.connected_future.done():
            self.connected_future.set_result(True)

    @mqtt_handle_decorator
    async def _mqtt_handle_notifications(self, prep: ParsedMessage):
        topics = prep.topics
        try:
            level = EventLevel.from_name(topics[2].upper())
        except Exception as e:
            logger.error(e)
            return

        ps.sendNotification(
            Notification(sender=self.name, message=prep.content, level=level)
        )

    @mqtt_handle_decorator
    async def _mqtt_handle_zone_control(self, prep: ParsedMessage):
        topics, element, command = prep

        if cfg.MQTT_CHALLENGE_SECRET is not None:
            command, user = self._validate_command_with_challenge(command)
            if command is None:
                return
        else:
            command, user = _extract_command_user(command)

        message = "Zone command: {}={} user: {}".format(element, command, user)
        logger.debug(message)
        self._publish_command_status(message)

        if not await self.alarm.control_zone(element, command):
            message = "Zone command refused: {}={} user: {}".format(
                element, command, user
            )
            logger.warning(message)
        else:
            message = "Zone command accepted: {}={} user: {}".format(
                element, command, user
            )

        self._publish_command_status(message)

    @mqtt_handle_decorator
    async def _mqtt_handle_partition_control(self, prep: ParsedMessage):
        topics, element, command = prep

        if cfg.MQTT_CHALLENGE_SECRET is not None:
            command, user = self._validate_command_with_challenge(command)
            if command is None:
                return
        else:
            command, user = _extract_command_user(command)

        command = cfg.MQTT_COMMAND_ALIAS.get(command, command)

        if command.startswith("code_toggle-"):
            tokens = command.split("-")
            if len(tokens) < 2:
                logger.warning("Invalid token length {}".format(len(tokens)))
                return

            if tokens[1] not in cfg.MQTT_TOGGLE_CODES:
                logger.warning("Invalid toggle code {}".format(tokens[1]))
                return

            if element.lower() == "all":
                command = "arm"

                for k, v in self.partitions.items():
                    # If "all" and a single partition is armed, default is
                    # to disarm
                    for k1, v1 in self.partitions[k].items():
                        if (
                            k1 == "arm" or k1 == "exit_delay" or k1 == "entry_delay"
                        ) and v1:
                            command = "disarm"
                            break

                    if command == "disarm":
                        break

            elif element in self.partitions:
                if (
                    "arm" in self.partitions[element]
                    and self.partitions[element]["arm"]
                ) or (
                    "exit_delay" in self.partitions[element]
                    and self.partitions[element]["exit_delay"]
                ):
                    command = "disarm"
                else:
                    command = "arm"
            else:
                logger.warning("Element {} not found".format(element))
                return

            ps.sendNotification(
                Notification(
                    sender="mqtt",
                    message="Command by {}: {}".format(
                        cfg.MQTT_TOGGLE_CODES[tokens[1]], command
                    ),
                    level=EventLevel.INFO,
                )
            )

        message = "Partition command: {}={} user: {}".format(element, command, user)
        logger.info(message)
        self._publish_command_status(message)

        if not await self.alarm.control_partition(element, command):
            message = "Partition command refused: {}={} user: {}".format(
                element, command, user
            )
            logger.warning(message)
        else:
            message = "Partition command accepted: {}={} user: {}".format(
                element, command, user
            )

        self._publish_command_status(message)

    @mqtt_handle_decorator
    async def _mqtt_handle_output_control(self, prep: ParsedMessage):
        topics, element, command = prep

        if cfg.MQTT_CHALLENGE_SECRET is not None:
            command, user = self._validate_command_with_challenge(command)

            if command is None:
                return
        else:
            command, user = _extract_command_user(command)

        message = "Output command: {}={} user: {}".format(element, command, user)
        logger.debug(message)
        self._publish_command_status(message)

        if not await self.alarm.control_output(element, command):
            message = "Output command refused: {}={} user: {}".format(
                element, command, user
            )
            logger.warning(message)
        else:
            message = "Output command accepted: {}={} user: {}".format(
                element, command, user
            )

        self._publish_command_status(message)

    @mqtt_handle_decorator
    async def _mqtt_handle_send_panic(self, prep: ParsedMessage):
        topics, partition, userid = prep

        panic_type = topics[2]

        if cfg.MQTT_CHALLENGE_SECRET is not None:
            userid, user = self._validate_command_with_challenge(userid)

            if userid is None:
                return
        else:
            userid, user = _extract_command_user(userid)

        message = "Send panic command: partition: {}, userid: {}, user: {}, type: {}".format(
            partition, userid, user, panic_type
        )
        logger.debug(message)
        self._publish_command_status(message)

        if not await self.alarm.send_panic(partition, panic_type, userid):
            message = "Send panic command refused: {}, userid: {}, user: {}, type: {}".format(
                partition, userid, user, panic_type
            )

            logger.warning(message)
        else:
            message = "Send panic command accepted: {}, userid: {}, user: {}, type: {}".format(
                partition, userid, user, panic_type
            )

        self._publish_command_status(message)

    @mqtt_handle_decorator
    async def _mqtt_handle_door_control(self, prep: ParsedMessage):
        topics, element, command = prep

        if cfg.MQTT_CHALLENGE_SECRET is not None:
            command, user = self._validate_command_with_challenge(command)

            if command is None:
                return
        else:
            command, user = _extract_command_user(command)

        message = "Door command: {}={} user=".format(element, command, user)

        logger.debug(message)
        self._publish_command_status(message)

        if not await self.alarm.control_door(element, command):
            message = "Door command refused: {}={} user: {}".format(
                element, command, user
            )
            logger.warning(message)
        else:
            message = "Door command accepted: {}={} user: {}".format(
                element, command, user
            )

        self._publish_command_status(message)

    def _handle_panel_event(self, event: Event):
        """
        Handle Live Event

        :param raw: object with properties (can have byte properties)
        :return:
        """

        if cfg.MQTT_PUBLISH_RAW_EVENTS:
            self.publish(
                "{}/{}/{}".format(
                    cfg.MQTT_BASE_TOPIC, cfg.MQTT_EVENTS_TOPIC, cfg.MQTT_RAW_TOPIC
                ),
                json.dumps(
                    event.props,
                    ensure_ascii=False,
                    cls=JSONByteEncoder,
                    default=str,
                    sort_keys=True,
                ),
                0,
                cfg.MQTT_RETAIN,
            )

    def _handle_panel_labels(self, data: dict):
        self.labels = data

        if not self.labels_future.done():
            self.labels_future.set_result(data)

    def _handle_panel_definitions(self, data: dict):
        self.definitions = data

        if not self.definitions_future.done():
            self.definitions_future.set_result(data)

    def _handle_panel_change(self, change: Change):
        attribute = change.property
        label = change.key
        value = change.new_value
        element_type = change.type

        """Handle Property Change"""
        if label not in self.partitions:
            self.partitions[label] = dict()

        self.partitions[label][attribute] = value
        self._publish(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}",
            element_type,
            label,
            attribute,
            value,
        )

    def _publish(
        self,
        base: str,
        element_type: str,
        label: str,
        attribute: str,
        value: [str, int, bool],
    ):
        if element_type in ELEMENT_TOPIC_MAP:
            element_topic = ELEMENT_TOPIC_MAP[element_type]
        else:
            element_topic = element_type

        if isinstance(value, dict):
            # This is fragile...
            if "/" in attribute and not attribute.startswith("/"):
                attribute = f"/{attribute}"

            for attr_name, attr_value in value.items():
                label_tp = f"{attribute}/{attr_name}"
                self._publish(base, element_type, label, label_tp, attr_value)
            return

        if cfg.MQTT_USE_NUMERIC_STATES:
            try:
                publish_value = int(value)
            except (TypeError, ValueError):
                logger.debug('Conversion int(%s) failed, use original value', value)
                publish_value = value
        else:
            publish_value = value

        self.publish(
            "{}/{}/{}/{}".format(base, element_topic, sanitize_key(label), attribute),
            "{}".format(publish_value),
            qos=cfg.MQTT_QOS,
            retain=cfg.MQTT_RETAIN,
        )

    def _on_ready(self):
        if cfg.MQTT_PUBLISH_DEFINITIONS:
            for element_type in self.definitions:  # zones, partitions
                labels = self.labels[element_type]
                definitions = self.definitions[element_type]
                for i in definitions:  # numeric index
                    if i not in labels:
                        continue

                    definition = {**(definitions[i]), "id": i}
                    for attribute in definition:  # attribute
                        if element_type == "user" and attribute == "code":
                            continue
                        self._publish(
                            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_DEFINITION_TOPIC}",
                            element_type,
                            labels[i]["key"],
                            attribute,
                            definition[attribute],
                        )

        if (
            cfg.MQTT_DASH_PUBLISH
            and len(list(self.labels.get("partition", {}).keys())) >= 2
        ):
            self._publish_dash(cfg.MQTT_DASH_TEMPLATE, self.labels.get("partition", {}))

        if cfg.MQTT_CHALLENGE_SECRET:
            logger.info("MQTT Commands authentication enabled")
            self._refresh_challenge()

    def _publish_dash(self, fname, partitions):
        # TODO: move to a separate component
        if len(list(partitions.keys())) < 2:
            return

        if os.path.exists(fname):
            with open(fname, "r") as f:
                data = f.read()

                for k in partitions.keys():
                    data = data.replace(f"__PARTITION{k}__", partitions[k]["label"])

                self.publish(cfg.MQTT_DASH_TOPIC, data, 2, True)
                logger.info(
                    "MQTT Dash panel published to {}".format(cfg.MQTT_DASH_TOPIC)
                )
        else:
            logger.warning("MQTT DASH Template not found: {}".format(fname))

    def _refresh_challenge(self):
        self.challenge = binascii.hexlify(os.urandom(16))
        self.publish(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            self.challenge,
            2,
            True,
        )

    def _validate_command_with_challenge(self, command):
        aux = command.strip().split(" ")

        challenge = self.challenge
        self._refresh_challenge()

        if challenge is None:
            logger.warning("No challenge set")
            return None, None

        if len(aux) != 2 and len(aux) != 3:
            logger.warning("Invalid command format. Authentication code required")
            return None, None

        user = None
        response = None

        if isinstance(cfg.MQTT_CHALLENGE_SECRET, dict):
            if aux[1] in cfg.MQTT_CHALLENGE_SECRET and len(aux) == 3:
                secret = cfg.MQTT_CHALLENGE_SECRET[aux[1]]
                user = aux[1]
                response = aux[2]
        elif isinstance(cfg.MQTT_CHALLENGE_SECRET, str):
            secret = cfg.MQTT_CHALLENGE_SECRET
            response = aux[1]
        else:
            logger.error(
                f"Authentication failed. Invalid setting MQTT_CHALLENGE_SECRET of type {type(cfg.MQTT_CHALLENGE_SECRET)}"
            )
            return None, None

        h = hashlib.new("SHA1")
        i = cfg.MQTT_CHALLENGE_ROUNDS
        text = f"{challenge}{secret}".encode("utf-8")

        while i > 0:
            h.update(text)
            i -= 1

        if response == h.hexdigest():
            message = f"Authentication success. user: {user}"
            ret = aux[0]  # Pass the command
        else:
            message = f"Authentication failed. user: {user}"
            ret = None
            user = None  # Clear user

        self._publish_command_status(message)
        logger.info(message)
        return ret, user
