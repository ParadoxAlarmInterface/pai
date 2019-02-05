import paho.mqtt.client as mqtt
import time
import logging
import json
import os
import re

from config import user as cfg

from paradox.lib.utils import SortableTuple
from paradox.interfaces import Interface

PARTITION_HOMEBRIDGE_COMMANDS = dict(
    STAY_ARM='arm_stay', AWAY_ARM='arm', NIGHT_ARM='arm_sleep', DISARM='disarm')
PARTITION_HOMEASSISTANT_COMMANDS = dict(
    armed_home='arm_stay', armed_away='arm', armed_sleep='arm_sleep', disarmed='disarm')

PARTITION_HOMEBRIDGE_STATES = dict(
    alarm='ALARM_TRIGGERED', stay_arm='STAY_ARM', arm='AWAY_ARM', sleep_arm='NIGHT_ARM', disarm='DISARMED')
PARTITION_HOMEASSISTANT_STATES = dict(
    alarm='triggered', stay_arm='armed_home', arm='armed_away', sleep_arm='armed_sleep', disarm='disarmed')

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)

#re_topic_dirty = re.compile(r'[+#/]')
re_topic_dirty = re.compile(r'\W')


def sanitize_topic_part(name):
    return re_topic_dirty.sub('_', name).strip('_')


class MQTTInterface(Interface):
    """Interface Class using MQTT"""
    name = 'mqtt'
    acceptsInitialState = True

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.mqtt = mqtt.Client("paradox_mqtt/{}".format(os.urandom(8).hex()))
        self.mqtt.on_message = self.handle_message
        self.mqtt.on_connect = self.handle_connect
        self.mqtt.on_disconnect = self.handle_disconnect
        self.connected = False

        self.cache = dict()

        self.armed = dict()

    def run(self):
        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        self.mqtt.connect(host=cfg.MQTT_HOST,
                          port=cfg.MQTT_PORT,
                          keepalive=cfg.MQTT_KEEPALIVE,
                          bind_address=cfg.MQTT_BIND_ADDRESS)

        self.mqtt.loop_start()
        last_republish = time.time()

        while True:
            item = self.queue.get()
            if item[1] == 'change':
                self.handle_change(item[2])
            elif item[1] == 'event':
                self.handle_event(item[2])
            elif item[1] == 'command':
                if item[2] == 'stop':
                    break
            if time.time() - last_republish > cfg.MQTT_REPUBLISH_INTERVAL:
                self.republish()
                last_republish = time.time()

        if self.connected:
            self.mqtt.disconnect()
            time.sleep(0.5)

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        self.mqtt.disconnect()
        self.logger.debug("Stopping MQTT Interface")
        self.queue.put_nowait(SortableTuple((0, 'command', 'stop')))
        self.mqtt.loop_stop()
        self.join()

    def event(self, raw):
        """ Enqueues an event"""
        self.queue.put_nowait(SortableTuple((2, 'event', raw)))

    def change(self, element, label, property, value):
        """ Enqueues a change """
        self.queue.put_nowait(SortableTuple(
            (2, 'change', (element, label, property, value))))

    # Handlers here
    def handle_message(self, client, userdata, message):
        """Handle message received from the MQTT broker"""
        self.logger.info("message topic={}, payload={}".format(
            message.topic, str(message.payload.decode("utf-8"))))

        if message.retain:
            return

        if self.alarm is None:
            self.logger.warning("No alarm. Ignoring command")
            return

        topic = message.topic.split(cfg.MQTT_BASE_TOPIC)[1]

        topics = topic.split("/")

        if len(topics) < 3:
            self.logger.error(
                "Invalid topic in mqtt message: {}".format(message.topic))
            return

        if topics[1] == cfg.MQTT_NOTIFICATIONS_TOPIC:
            if topics[2].upper() == "CRITICAL":
                level = logging.CRITICAL
            elif topics[2].upper() == "INFO":
                level = logging.INFO
            else:
                self.logger.error(
                    "Invalid notification level: {}".format(topics[2]))
                return

            payload = message.payload.decode("latin").strip()
            self.notification_handler.notify(self.name, payload, level)
            return

        if topics[1] != cfg.MQTT_CONTROL_TOPIC:
            self.logger.error(
                "Invalid subtopic in mqtt message: {}".format(message.topic))
            return

        command = message.payload.decode("latin").strip()
        element = topics[3]

        # Process a Zone Command
        if topics[2] == cfg.MQTT_ZONE_TOPIC:
            if not self.alarm.control_zone(element, command):
                self.logger.warning(
                    "Zone command refused: {}={}".format(element, command))

        # Process a Partition Command
        elif topics[2] == cfg.MQTT_PARTITION_TOPIC:

            if command in PARTITION_HOMEBRIDGE_COMMANDS and cfg.MQTT_HOMEBRIDGE_ENABLE:
                command = PARTITION_HOMEBRIDGE_COMMANDS[command]
            elif command in PARTITION_HOMEASSISTANT_COMMANDS and cfg.MQTT_HOMEASSISTANT_ENABLE:
                command = PARTITION_HOMEASSISTANT_COMMANDS[command]

            if command.startswith('code_toggle-'):
                tokens = command.split('-')
                if len(tokens) < 2:
                    return

                if tokens[1] not in cfg.MQTT_TOGGLE_CODES:
                    self.logger.warning("Invalid toggle code {}".format(tokens[1]))
                    return

                if element.lower() == 'all':
                    command = 'arm'

                    for k, v in self.partitions.items():
                        # If "all" and a single partition is armed, default is
                        # to desarm
                        for k1, v1 in self.partitions[k].items():
                            if (k1 == 'arm' or k1 == 'exit_delay' or k1 == 'entry_delay') and v1:
                                command = 'disarm'
                                break

                        if command == 'disarm':
                            break

                elif element in self.partitions:
                    if ('arm' in self.partitions[element] and self.partitions[element]['arm'])\
                            or ('exit_delay' in self.partitions[element] and self.partitions[element]['exit_delay']):
                        command = 'disarm'
                    else:
                        command = 'arm'
                else:
                    self.logger.debug("Element {} not found".format(element))
                    return

                self.notification_handler.notify('mqtt', "Command by {}: {}".format(
                    cfg.MQTT_TOGGLE_CODES[tokens[1]], command), logging.INFO)

            self.logger.debug("Partition command: {} = {}".format(element, command))
            if not self.alarm.control_partition(element, command):
                self.logger.warning(
                    "Partition command refused: {}={}".format(element, command))

        # Process an Output Command
        elif topics[2] == cfg.MQTT_OUTPUT_TOPIC:
            self.logger.debug("Output command: {} = {}".format(element, command))

            if not self.alarm.control_output(element, command):
                self.logger.warning(
                    "Output command refused: {}={}".format(element, command))
        else:
            self.logger.error("Invalid control property {}".format(topics[2]))

    def handle_disconnect(self, mqttc, userdata, rc):
        self.logger.info("MQTT Broker Disconnected")
        self.connected = False

        time.sleep(1)

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        self.mqtt.connect(host=cfg.MQTT_HOST,
                          port=cfg.MQTT_PORT,
                          keepalive=cfg.MQTT_KEEPALIVE,
                          bind_address=cfg.MQTT_BIND_ADDRESS)

    def handle_connect(self, mqttc, userdata, flags, result):
        self.logger.info("MQTT Broker Connected")

        self.connected = True
        self.logger.debug(
            "Subscribing to topics in {}/{}".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC))
        self.mqtt.subscribe(
            "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
                              cfg.MQTT_CONTROL_TOPIC, "#"))

        self.mqtt.subscribe(
            "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
                              cfg.MQTT_NOTIFICATIONS_TOPIC, "#"))

        self.mqtt.will_set('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                             cfg.MQTT_INTERFACE_TOPIC,
                                             self.__class__.__name__),
                           'offline', 0, cfg.MQTT_RETAIN)

        self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                       cfg.MQTT_INTERFACE_TOPIC,
                                       self.__class__.__name__),
                     'online', 0, cfg.MQTT_RETAIN)

    def handle_event(self, raw):
        """Handle Live Event"""

        if cfg.MQTT_PUBLISH_RAW_EVENTS:
            self.publish('{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                        cfg.MQTT_EVENTS_TOPIC,
                                        cfg.MQTT_RAW_TOPIC),
                         json.dumps(raw.props), 0, cfg.MQTT_RETAIN)

    def handle_change(self, raw):
        element, label, attribute, value = raw
        """Handle Property Change"""

        # Keep track of ARM state
        if element == 'partition':
            if label not in self.partitions:
                self.partitions[label] = dict()

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
                self.handle_change_external(element, label, attribute, value, element_topic,
                                            PARTITION_HOMEBRIDGE_STATES, cfg.MQTT_HOMEBRIDGE_SUMMARY_TOPIC, 'hb')

            if cfg.MQTT_HOMEASSISTANT_ENABLE:
                self.handle_change_external(element, label, attribute, value, element_topic,
                                            PARTITION_HOMEASSISTANT_STATES, cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC,
                                            'hass')

    def handle_change_external(self, element, label, attribute,
                               value, element_topic, states_map,
                               summary_topic, service):

        if service not in self.armed:
            self.armed[service] = dict()

        if label not in self.armed[service]:
            self.armed[service][label] = (None, None, False)

        # Property changing to True: Alarm or arm
        if value:
            if attribute == 'alarm':
                state = states_map['alarm']
                self.armed[service][label][2] = True

            # only process if not armed already
            elif self.armed[service][label][0] is None:
                if attribute == 'stay_arm':
                    state = states_map['stay_arm']
                elif attribute == 'arm':
                    state = states_map['arm']
                elif attribute == 'sleep_arm':
                    state = states_map['sleep_arm']
                else:
                    return

                self.armed[service][label] = (attribute, state, self.armed[service][label][2])
            else:
                return  # Do not publish a change

        # Property changing to False: Disarm or alarm stop
        else:
            # Alarm stopped
            if attribute == 'alarm' and self.armed[service][label][2]:
                state = self.armed[service][label][1]
                self.armed[service][label][2] = False

            elif attribute in ['stay_arm', 'arm', 'sleep_arm'] and self.armed[service][label][0] == attribute:
                state = states_map['disarm']
                self.armed[service][label] = (None, None, self.armed[service][label][2])
            else:
                return  # Do not publish a change

        self.publish('{}/{}/{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                             cfg.MQTT_STATES_TOPIC,
                                             element_topic,
                                             sanitize_topic_part(label),
                                             summary_topic),
                     "{}".format(state), 0, cfg.MQTT_RETAIN)

    def publish(self, topic, value, qos, retain):
        self.cache[topic] = {'value': value, 'qos': qos, 'retain': retain}
        self.mqtt.publish(topic, value, qos, retain)

    def republish(self):
        for k in list(self.cache.keys()):
            v = self.cache[k]
            self.mqtt.publish(k, v['value'], v['qos'], v['retain'])
