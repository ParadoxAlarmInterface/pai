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
from .core import AbstractMQTTInterface

logger = logging.getLogger('PAI').getChild(__name__)

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)

# re_topic_dirty = re.compile(r'[+#/]')
re_topic_dirty = re.compile(r'\W')

PreparseResponse = namedtuple('preparse_response', 'topics element content')


def sanitize_topic_part(name):
    return re_topic_dirty.sub('_', name).strip('_')


class BasicMQTTInterface(AbstractMQTTInterface):
    name = 'basic_mqtt'

    def __init__(self):
        super(BasicMQTTInterface, self).__init__()

        self.cache = dict()
        self.armed = dict()
        self.partitions = {}
        self.last_republish = time.time()

    def run(self):
        required_mappings = 'alarm,arm,arm_stay,arm_sleep,disarm'.split(',')
        if cfg.MQTT_HOMEBRIDGE_ENABLE:
            self._check_config_mappings('MQTT_PARTITION_HOMEBRIDGE_STATES', required_mappings)
        if cfg.MQTT_HOMEASSISTANT_ENABLE:
            self._check_config_mappings('MQTT_PARTITION_HOMEASSISTANT_STATES', required_mappings)

        ps.subscribe(self._handle_panel_change, "changes")
        ps.subscribe(self._handle_panel_event, "events")

        self.last_republish = time.time()

        self.mqtt.message_callback_add(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_OUTPUT_TOPIC),
            self._mqtt_handle_output_control
        )
        self.mqtt.message_callback_add(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_ZONE_TOPIC),
            self._mqtt_handle_zone_control
        )
        self.mqtt.message_callback_add(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC, cfg.MQTT_PARTITION_TOPIC),
            self._mqtt_handle_partition_control
        )
        self.mqtt.message_callback_add(
            "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_NOTIFICATIONS_TOPIC, "#"),
            self._mqtt_handle_notifications
        )

        super().run()

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

        content = message.payload.decode("latin").strip()

        element = None
        if len(topics) >= 4:
            element = topics[3]

        return PreparseResponse(topics, element, content)

    def _mqtt_handle_notifications(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics = prep.topics
            if topics[2].upper() == "CRITICAL":
                level = logging.CRITICAL
            elif topics[2].upper() == "INFO":
                level = logging.INFO
            else:
                logger.error(
                    "Invalid notification level: {}".format(topics[2]))
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
            # if command in cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS and cfg.MQTT_HOMEBRIDGE_ENABLE:
            #     command = cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS[command]
            # elif command in cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS and cfg.MQTT_HOMEASSISTANT_ENABLE:
            #     command = cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS[command]

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

        if element == 'partition':
            if cfg.MQTT_HOMEBRIDGE_ENABLE:
                self._handle_change_external(element, label, attribute, value, element_topic,
                                             cfg.MQTT_PARTITION_HOMEBRIDGE_STATES, cfg.MQTT_HOMEBRIDGE_SUMMARY_TOPIC,
                                             'hb')

            if cfg.MQTT_HOMEASSISTANT_ENABLE:
                self._handle_change_external(element, label, attribute, value, element_topic,
                                             cfg.MQTT_PARTITION_HOMEASSISTANT_STATES,
                                             cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC,
                                             'hass')

    def _check_config_mappings(self, config_parameter, required_mappings):
        # Check states_map
        keys = getattr(cfg, config_parameter).keys()
        missing_mappings = [k for k in required_mappings if k not in keys]
        if len(missing_mappings):
            logger.warning(', '.join(missing_mappings) + " keys are missing from %s config." % config_parameter)

    def _handle_change_external(self, element, label, attribute,
                                value, element_topic, states_map,
                                summary_topic, service):

        if service not in self.armed:
            self.armed[service] = dict()

        if label not in self.armed[service]:
            self.armed[service][label] = dict(attribute=None, state=None, alarm=False)

        # Property changing to True: Alarm or arm
        if value:
            if attribute in ['alarm', 'bell_activated', 'strobe_alarm', 'silent_alarm', 'audible_alarm'] and not \
                    self.armed[service][label]['alarm']:
                state = states_map['alarm']
                self.armed[service][label]['alarm'] = True

            # only process if not armed already
            elif self.armed[service][label]['attribute'] is None:
                if attribute == 'arm_stay':
                    state = states_map['arm_stay']
                elif attribute == 'arm':
                    state = states_map['arm']
                elif attribute == 'arm_sleep':
                    state = states_map['arm_sleep']
                else:
                    return

                self.armed[service][label]['attribute'] = attribute
                self.armed[service][label]['state'] = state
            else:
                return  # Do not publish a change

        # Property changing to False: Disarm or alarm stop
        else:
            # Alarm stopped
            if attribute in ['alarm', 'strobe_alarm', 'audible_alarm', 'bell_activated', 'silent_alarm'] and \
                    self.armed[service][label]['alarm']:
                state = self.armed[service][label]['state']  # Restore the ARM state
                self.armed[service][label]['alarm'] = False  # Reset alarm state

            elif attribute in ['arm_stay', 'arm', 'arm_sleep'] and self.armed[service][label]['attribute'] == attribute:
                state = states_map['disarm']
                self.armed[service][label] = dict(attribute=None, state=None, alarm=False)
            else:
                return  # Do not publish a change

        self.publish('{}/{}/{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                             cfg.MQTT_STATES_TOPIC,
                                             element_topic,
                                             sanitize_topic_part(label),
                                             summary_topic),
                     "{}".format(state), 0, cfg.MQTT_RETAIN)

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
