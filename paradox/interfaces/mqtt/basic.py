import json
import logging
import os
import typing
from collections import namedtuple

from paho.mqtt.client import MQTTMessage, Client

from paradox.config import config as cfg
from paradox.event import EventLevel, Event, Change, Notification
from paradox.lib import ps
from paradox.lib.utils import JSONByteEncoder, sanitize_key
from .core import AbstractMQTTInterface, ELEMENT_TOPIC_MAP

logger = logging.getLogger('PAI').getChild(__name__)

ParsedMessage = namedtuple('parsed_message', 'topics element content')


def mqtt_handle_decorator(func: typing.Callable[["BasicMQTTInterface", ParsedMessage], None]):
    def wrapper(self: "BasicMQTTInterface", client: Client, userdata, message: MQTTMessage):
        try:
            logger.info("message topic={}, payload={}".format(
                message.topic, str(message.payload.decode("utf-8"))))

            if message.retain:
                logger.warning("Ignoring retained commands")
                return

            if self.alarm is None:
                logger.warning("No alarm. Ignoring command")
                return

            topic = message.topic.split(cfg.MQTT_BASE_TOPIC)[1]

            topics = topic.split("/")

            if len(topics) < 3:
                logger.error(
                    "Invalid topic in mqtt message: {}".format(message.topic))
                return

            content = message.payload.decode("utf-8").strip()

            element = None
            if len(topics) >= 4:
                element = topics[3]

            func(self, ParsedMessage(topics, element, content))
        except Exception:
            logger.exception("Failed to execute command")

    return wrapper


class BasicMQTTInterface(AbstractMQTTInterface):
    name = 'basic_mqtt'

    def __init__(self):
        super().__init__()

        self.partitions = {}
        self.definitions = {}
        self.labels = {}

    async def run(self):
        ps.subscribe(self._handle_panel_labels, "labels_loaded")
        ps.subscribe(self._handle_panel_definitions, "definitions_loaded")
        ps.subscribe(self._handle_panel_change, "changes")
        ps.subscribe(self._handle_panel_event, "events")
        ps.subscribe(self._handle_connected, "connected")
        

        await super().run()

    def on_connect(self, mqttc, userdata, flags, result):
        super().on_connect(mqttc, userdata, flags, result)
        self.subscribe_callback(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_OUTPUT_TOPIC),
            self._mqtt_handle_output_control
        )
        self.subscribe_callback(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_ZONE_TOPIC),
            self._mqtt_handle_zone_control
        )
        self.subscribe_callback(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_PARTITION_TOPIC),
            self._mqtt_handle_partition_control
        )
        self.subscribe_callback(
            "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_NOTIFICATIONS_TOPIC, "#"),
            self._mqtt_handle_notifications
        )

    @mqtt_handle_decorator
    def _mqtt_handle_notifications(self, prep: ParsedMessage):
        topics = prep.topics
        try:
            level = EventLevel.from_name(topics[2].upper())
        except Exception as e:
            logger.error(e)
            return

        ps.sendNotification(Notification(sender=self.name, message=prep.content, level=level))

    @mqtt_handle_decorator
    def _mqtt_handle_zone_control(self, prep: ParsedMessage):
        topics, element, command = prep
        if not self.alarm.control_zone(element, command):
            logger.warning("Zone command refused: {}={}".format(element, command))

    @mqtt_handle_decorator
    def _mqtt_handle_partition_control(self, prep: ParsedMessage):
        topics, element, command = prep
        command = cfg.MQTT_COMMAND_ALIAS.get(command, command)

        if command.startswith('code_toggle-'):
            tokens = command.split('-')
            if len(tokens) < 2:
                logger.warning("Invalid token length {}".format(len(tokens)))
                return

            if tokens[1] not in cfg.MQTT_TOGGLE_CODES:
                logger.warning("Invalid toggle code {}".format(tokens[1]))
                return

            if element.lower() == 'all':
                command = 'arm'

                for k, v in self.partitions.items():
                    # If "all" and a single partition is armed, default is
                    # to disarm
                    for k1, v1 in self.partitions[k].items():
                        if (k1 == 'arm' or k1 == 'exit_delay' or k1 == 'entry_delay') and v1:
                            command = 'disarm'
                            break

                    if command == 'disarm':
                        break

            elif element in self.partitions:
                if ('arm' in self.partitions[element] and self.partitions[element]['arm']) \
                        or ('exit_delay' in self.partitions[element] and self.partitions[element]['exit_delay']):
                    command = 'disarm'
                else:
                    command = 'arm'
            else:
                logger.warning("Element {} not found".format(element))
                return

            ps.sendNotification(Notification(sender="mqtt", message="Command by {}: {}".format(
                    cfg.MQTT_TOGGLE_CODES[tokens[1]], command), level=EventLevel.INFO))

        logger.info("Partition command: {} = {}".format(element, command))
        if not self.alarm.control_partition(element, command):
            logger.warning("Partition command refused: {}={}".format(element, command))

    @mqtt_handle_decorator
    def _mqtt_handle_output_control(self, prep: ParsedMessage):
        topics, element, command = prep
        logger.debug("Output command: {} = {}".format(element, command))

        if not self.alarm.control_output(element, command):
            logger.warning("Output command refused: {}={}".format(element, command))

    def _handle_panel_event(self, event: Event):
        """
        Handle Live Event

        :param raw: object with properties (can have byte properties)
        :return:
        """

        if cfg.MQTT_PUBLISH_RAW_EVENTS:
            self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                        cfg.MQTT_EVENTS_TOPIC,
                                        cfg.MQTT_RAW_TOPIC),
                         json.dumps(event.props, ensure_ascii=False, cls=JSONByteEncoder, default=str, sort_keys=True), 0, cfg.MQTT_RETAIN)

    def _handle_panel_labels(self, data: dict):
        self.labels = data

    def _handle_panel_definitions(self, data: dict):
        self.definitions = data
                
    def _handle_connected(self):
        # After we get 2 partitions, lets publish a dashboard
        if cfg.MQTT_DASH_PUBLISH and len(self.partitions) == 2:
            self._publish_dash(cfg.MQTT_DASH_TEMPLATE, list(self.partitions.keys()))

        for element_type in self.definitions: # zones, partitions
            labels = self.labels[element_type]
            definitions = self.definitions[element_type]
            for i in definitions:  # numeric index
                if i not in labels:
                    continue
                
                for attribute in definitions[i]:  # attribute
                    self._publish(f'{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_DEFINITION_TOPIC}',
                                  element_type,
                                  labels[i]['key'],
                                  attribute,
                                  definitions[i][attribute])
        
    def _handle_panel_change(self, change: Change):
        attribute = change.property
        label = change.key
        value = change.new_value
        element_type = change.type

        """Handle Property Change"""
        if label not in self.partitions:
            self.partitions[label] = dict()

        self.partitions[label][attribute] = value
        self._publish(f'{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}', element_type, label, attribute, value)
        
    def _publish(self, base: str, element_type: str, label: str, attribute: str, value: [str, int, bool]):
        if element_type in ELEMENT_TOPIC_MAP:
            element_topic = ELEMENT_TOPIC_MAP[element_type]
        else:
            element_topic = element_type
        
        if isinstance(value, dict):
            # This is fragile...
            if '/' in attribute and not attribute.startswith('/'):
                attribute = f"/{attribute}"

            for attr_name, attr_value in value.items():    
                label_tp = f"{attribute}/{attr_name}"
                self._publish(base, element_type, label, label_tp, attr_value)
            return

        if cfg.MQTT_USE_NUMERIC_STATES:
            publish_value = int(value)
        else:
            publish_value = value

        self.publish('{}/{}/{}/{}'.format(base,
                                             element_topic,
                                             sanitize_key(label),
                                             attribute),
                     "{}".format(publish_value), 0, cfg.MQTT_RETAIN)

    def _publish_dash(self, fname, partitions):
        # TODO: move to a separate component
        if len(partitions) < 2:
            return

        if os.path.exists(fname):
            with open(fname, 'r') as f:
                data = f.read()
                data = data.replace('__PARTITION1__', partitions[0]).replace('__PARTITION2__', partitions[1])
                self.mqtt.publish(cfg.MQTT_DASH_TOPIC, data, 2, True)
                logger.info("MQTT Dash panel published to {}".format(cfg.MQTT_DASH_TOPIC))
        else:
            logger.warning("MQTT DASH Template not found: {}".format(fname))
