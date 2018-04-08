import paho.mqtt.client as mqtt
import time
import logging
import datetime
import json

from config_defaults import *
from config import *

logger = logging.getLogger('PAI').getChild(__name__)


class MQTTInterface():
    """Interface Class using MQTT"""

    def __init__(self):
        self.callback = None
        self.mqtt = mqtt.Client("MQTTParadox")
        self.mqtt.on_message = self.handle_message
        self.mqtt.on_connect = self.handle_connect
        self.mqtt.on_disconnect = self.handle_disconnect
        self.connected = False
        self.alarm = None

    def set_alarm(self, alarm):
        self.alarm = alarm

    def handle_message(self, client, userdata, message):
        """Handle message received from the MQTT broker"""
        logger.info("message topic={}, payload={}".format(
            message.topic, str(message.payload.decode("utf-8"))))

        topics = message.topic.split("/")

        if len(topics) < 3:
            logger.error(
                "Invalid topic in mqtt message: {}".format(message.topic))
            return

        if topics[1] != MQTT_CONTROL_TOPIC:
            logger.error(
                "Invalid subtopic in mqtt message: {}".format(message.topic))
            return

        command = self.normalize_mqtt_payload(message.payload)
        element = topics[3]

        # Process a Zone Command
        if topics[2] == MQTT_ZONE_TOPIC:
            if command not in ['bypass', 'clear_bypass']:
                logger.error("Invalid command for Zone {}".format(command))
                return

            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))

        # Process a Partition Command
        elif topics[2] == MQTT_PARTITION_TOPIC:
            if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
                logger.error(
                    "Invalid command for Partition {}".format(command))
                return

            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))
       
        # Process an Output Command
        elif topics[2] == MQTT_OUTPUT_TOPIC:
            if command not in ['on', 'off', 'pulse']:
                logger.error("Invalid command for Output {}".format(command))
                return

            if not self.alarm.control_output(element, command):
                logger.warning(
                    "Output command refused: {}={}".format(element, command))
        else:
            logger.error("Invalid control property {}".format(topics[2]))

    def handle_disconnect(self, mqttc, userdata, rc):
        logger.info("MQTT Broker Disconnected")
        self.connected = False
        self.mqtt.loop_stop()

    def handle_connect(self, mqttc, userdata, flags, result):
        logger.info("MQTT Broker Connected")

        self.connected = True

        self.mqtt.subscribe(
            "{}/{}/{}".format(MQTT_BASE_TOPIC,
                              MQTT_CONTROL_TOPIC, "#"))
        
        self.mqtt.will_set('{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                             MQTT_INTERFACE_TOPIC,
                                             self.__class__.__name__), 
                            'offline', 0, MQTT_RETAIN)

        

        self.mqtt.publish('{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                            MQTT_INTERFACE_TOPIC,
                                            self.__class__.__name__),
                          'online', 0, MQTT_RETAIN)

    def start(self):
        """Connect to the MQTT Server"""

        if MQTT_USERNAME is not None and MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=MQTT_USERNAME, password=MQTT_PASSWORD)

        self.mqtt.connect(host=MQTT_HOST,
                          port=MQTT_PORT,
                          keepalive=MQTT_KEEPALIVE,
                          bind_address=MQTT_BIND_ADDRESS)
        
        self.mqtt.loop_start()

    def set_callback(self, callback):
        self.callback = callback

    def stop(self):
        if self.connected:
            self.mqtt.disconnect()
            time.sleep(0.5)

    def normalize_mqtt_payload(self, payload):
        payload = payload.decode('utf-8').strip().lower().replace(' ', '_')

        if payload in ['true', 'on', '1', 'enable']:
            return 'on'
        elif payload in ['false', 'off', '0', 'disable']:
            return 'off'
        elif payload in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return payload

        return None

    def event(self, element, label, message, raw):
        """Handle Live Event"""
        logger.debug("Live Event: element={}, label={}, message={}, raw={}".format(
            element,
            label,
            message,
            raw))

        if MQTT_PUBLISH_RAW_EVENTS:
            raw['time'] = "{}".format(datetime.datetime.now())
            self.mqtt.publish('{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                                MQTT_EVENTS_TOPIC,
                                                MQTT_RAW_TOPIC),
                              json.dumps(raw), 0, MQTT_RETAIN)

    def change(self, element, label, property, value):
        """Handle Property Change"""
        logger.debug("Property Change: element={}, label={}, property={}, value={}".format(
            element,
            label,
            property,
            value))
        
        if IGNORE_UNNAMED_ZONES and element=='zone' and label.startswith("Zone "):
            return
        
        if IGNORE_UNNAMED_PARTITIONS and element=='partition' and label.startswith("Partition "):
            return
        
        if IGNORE_UNNAMED_OUTPUTS and element=='output' and label.startswith("Output "):
            return

        self.mqtt.publish('{}/{}/{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                            MQTT_EVENTS_TOPIC,
                                            element,
                                            label,
                                            property),
                          "{}".format(value), 0, MQTT_RETAIN)

