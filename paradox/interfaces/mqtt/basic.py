import json
import logging
import os
import re
import time
import typing
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import JSONByteEncoder
from paradox.event import EventLevel
from .core import AbstractMQTTInterface, sanitize_topic_part, ELEMENT_TOPIC_MAP

logger = logging.getLogger('PAI').getChild(__name__)

PreparseResponse = namedtuple('preparse_response', 'topics element content')


class BasicMQTTInterface(AbstractMQTTInterface):
    name = 'basic_mqtt'

    def __init__(self):
        super().__init__()

        self.cache = dict()
        self.armed = dict()
        self.partitions = {}
        self.last_republish = time.time()

    async def run(self):
        ps.subscribe(self._handle_panel_change, "changes")
        ps.subscribe(self._handle_panel_event, "events")

        self.last_republish = time.time()

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

    def run_loop(self, queue_item):
        if time.time() - self.last_republish > cfg.MQTT_REPUBLISH_INTERVAL:
            self.republish()
            self.last_republish = time.time()

    def publish(self, topic, value, qos, retain):
        self.cache[topic] = {'value': value, 'qos': qos, 'retain': retain}
        super().publish(topic, value, qos, retain)

    def _preparse_message(self, message) -> typing.Optional[PreparseResponse]:
        logger.info("message topic={}, payload={}".format(
            message.topic, str(message.payload.decode("utf-8"))))

        if message.retain:
            logger.warning("Ignoring retained commands")
            return None

        if self.alarm is None:
            logger.warning("No alarm. Ignoring command")
            return None

        topic = message.topic.split(cfg.MQTT_BASE_TOPIC)[1]

        topics = topic.split("/")

        if len(topics) < 3:
            logger.error(
                "Invalid topic in mqtt message: {}".format(message.topic))
            return None

        content = message.payload.decode("utf-8").strip()

        element = None
        if len(topics) >= 4:
            element = topics[3]

        return PreparseResponse(topics, element, content)

    def _mqtt_handle_notifications(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics = prep.topics
            try:
                level = EventLevel.from_name(topics[2].upper())
            except Exception as e:
                logger.error(e)
                return

            ps.sendMessage("notifications", message=dict(source=self.name, payload=prep.content, level=level))

    def _mqtt_handle_zone_control(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics, element, command = prep
            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))

    def _mqtt_handle_partition_control(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics, element, command = prep

            if command.startswith('code_toggle-'):
                tokens = command.split('-')
                if len(tokens) < 2:
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
                    logger.debug("Element {} not found".format(element))
                    return

                ps.sendMessage('notifications', message=dict(
                    source="mqtt",
                    message="Command by {}: {}".format(
                        cfg.MQTT_TOGGLE_CODES[tokens[1]], command),
                    level=logging.INFO))

            logger.debug("Partition command: {} = {}".format(element, command))
            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))

    def _mqtt_handle_output_control(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics, element, command = prep
            logger.debug("Output command: {} = {}".format(element, command))

            if not self.alarm.control_output(element, command):
                logger.warning(
                    "Output command refused: {}={}".format(element, command))

    def _handle_panel_event(self, event):
        """
        Handle Live Event

        :param raw: object with properties (can have byte properties)
        :return:
        """

        if cfg.MQTT_PUBLISH_RAW_EVENTS:
            self.publish('{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                        cfg.MQTT_EVENTS_TOPIC,
                                        cfg.MQTT_RAW_TOPIC),
                         json.dumps(event.props, ensure_ascii=False, cls=JSONByteEncoder), 0, cfg.MQTT_RETAIN)

    def _handle_panel_change(self, change):
        logger.debug(change)

        attribute = change['property']
        label = change['label']
        value = change['value']
        initial = change['initial']
        element = change['type']

        """Handle Property Change"""

        # Keep track of ARM state
        if element == 'partition':
            if label not in self.partitions:
                self.partitions[label] = dict()

                # After we get 2 partitions, lets publish a dashboard
                if cfg.MQTT_DASH_PUBLISH and len(self.partitions) == 2:
                    self._publish_dash(cfg.MQTT_DASH_TEMPLATE, list(self.partitions.keys()))

            self.partitions[label][attribute] = value

        if element in ELEMENT_TOPIC_MAP:
            element_topic = ELEMENT_TOPIC_MAP[element]
        else:
            element_topic = element

        if cfg.MQTT_USE_NUMERIC_STATES:
            publish_value = int(value)
        else:
            publish_value = value

        self.publish('{}/{}/{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                             cfg.MQTT_STATES_TOPIC,
                                             element_topic,
                                             sanitize_topic_part(label),
                                             attribute),
                     "{}".format(publish_value), 0, cfg.MQTT_RETAIN)

    def republish(self):
        for k in list(self.cache.keys()):
            v = self.cache[k]
            self.mqtt.publish(k, v['value'], v['qos'], v['retain'])

    def _publish_dash(self, fname, partitions):
        if len(partitions) < 2:
            return

        if os.path.exists(fname):
            with open(fname, 'r') as f:
                data = f.read()
                data = data.replace('__PARTITION1__', partitions[0]).replace('__PARTITION2__', partitions[1])
                self.mqtt.publish(cfg.MQTT_DASH_TOPIC, data, 2, True)
                logger.info("MQTT Dash panel published to {}".format(cfg.MQTT_DASH_TOPIC))
        else:
            logger.warn("MQTT DASH Template not found: {}".format(fname))
