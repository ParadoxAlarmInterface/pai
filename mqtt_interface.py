import paho.mqtt.client as mqtt
import time
import logging
import datetime
import json
from threading import Thread
import queue
from config_defaults import *
from config import *

from utils import SortableTuple

logger = logging.getLogger('PAI').getChild(__name__)

class MQTTInterface(Thread):
    """Interface Class using MQTT"""
    name = 'mqtt'

    def __init__(self):
        Thread.__init__(self)

        self.callback = None
        self.mqtt = mqtt.Client("MQTTParadox")
        self.mqtt.on_message = self.handle_message
        self.mqtt.on_connect = self.handle_connect
        self.mqtt.on_disconnect = self.handle_disconnect
        self.connected = False
        self.alarm = None
        self.partitions = {}
        self.queue = queue.PriorityQueue()

        self.notification_handler = None
        self.cache = dict()
        
    def run(self):
        if MQTT_USERNAME is not None and MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=MQTT_USERNAME, password=MQTT_PASSWORD)

        self.mqtt.connect(host=MQTT_HOST,
                          port=MQTT_PORT,
                          keepalive=MQTT_KEEPALIVE,
                          bind_address=MQTT_BIND_ADDRESS)
    
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
            if time.time() - last_republish > MQTT_REPUBLISH_INTERVAL:
                self.republish()
                last_republish = time.time()

        if self.connected:
            self.mqtt.disconnect()
            time.sleep(0.5)

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        self.mqtt.disconnect()
        logger.debug("Stopping MQTT Interface")
        self.queue.put_nowait(SortableTuple((0, 'command', 'stop')))
        self.mqtt.loop_stop()
        self.join()

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm
    
    def set_notify(self, handler):
        """ Set the notification handler"""
        self.notification_handler = handler

    def event(self, raw):
        """ Enqueues an event"""
        self.queue.put_nowait(SortableTuple((2, 'event', raw)))

    def change(self, element, label, property, value):
        """ Enqueues a change """
        self.queue.put_nowait(SortableTuple((2, 'change', (element, label, property, value))))

    # not supported
    def notify(self, source, message, level):
        pass

    ## Handlers here
    def handle_message(self, client, userdata, message):
        """Handle message received from the MQTT broker"""
        logger.info("message topic={}, payload={}".format(
            message.topic, str(message.payload.decode("utf-8"))))

        if self.alarm is None:
            logger.warning("No alarm. Ignoring command")
            return

        topics = message.topic.split("/")

        if len(topics) < 3:
            logger.error(
                "Invalid topic in mqtt message: {}".format(message.topic))
            return
        
        if topics[1] == MQTT_NOTIFICATIONS_TOPIC:
            if topics[2].upper() == "CRITICAL":
                level = logging.CRITICAL
            elif topics[2].upper() == "INFO":
                level = logging.INFO
            else:
                logger.error(
                    "Invalid notification level: {}".format(topics[2]))
                return

            payload = message.payload.decode("latin").strip()
            self.notification_handler.notify(self.name, payload, level)
            return


        if topics[1] != MQTT_CONTROL_TOPIC:
            logger.error(
                "Invalid subtopic in mqtt message: {}".format(message.topic))
            return        
        
        command = message.payload.decode("latin").strip()
        element = topics[3]

        # Process a Zone Command
        if topics[2] == MQTT_ZONE_TOPIC:
            if command not in self.alarm.ZONE_ACTIONS:
                logger.error("Invalid command for Zone {}".format(command))
                return

            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))

        # Process a Partition Command
        elif topics[2] == MQTT_PARTITION_TOPIC:
    
            if command.startswith('code_toggle-'):
                tokens = command.split('-')
                if len(tokens) < 2:
                    return
                
                if tokens[1] not in MQTT_TOGGLE_CODES:
                    logger.warning("Invalid toggle code {}".format(tokens[1]))
                    return

                if element.lower() == 'all':
                    command = 'arm'

                    for k,v in self.partitions.items():
                        # If "all" and a single partition is armed, default is to desarm
                        for k1,v1 in self.partitions[k].items():
                            if (k1 == 'arm' or k1 == 'exit_delay' or k1 == 'entry_delay') and v1:
                                command = 'disarm'
                                break
                        
                        if command == 'disarm':
                            break


                elif element in self.partitions:
                    if ('arm' in self.partitions[element] and self.partitions[element]['arm']) or ('exit_delay' in self.partitions[element] and self.partitions[element]['exit_delay']):
                        command = 'disarm'
                    else:
                        command = 'arm'
                
                else:
                    logger.debug("Element {} not found".format(element))
                    return

                logger.debug("Effective command: {} = {}".format(element, command))

                if command not in self.alarm.PARTITION_ACTIONS:
                    logger.error(
                        "Invalid command for Partition {}".format(command))
                    return
            
                self.notification_handler.notify('mqtt', "Command by {}: {}".format(MQTT_TOGGLE_CODES[tokens[1]], command), logging.INFO)

            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))
       
        # Process an Output Command
        elif topics[2] == MQTT_OUTPUT_TOPIC:
            if command not in self.alarm.PGM_ACTIONS:
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
        
        time.sleep(1)

        if MQTT_USERNAME is not None and MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=MQTT_USERNAME, password=MQTT_PASSWORD)

        self.mqtt.connect(host=MQTT_HOST,
                          port=MQTT_PORT,
                          keepalive=MQTT_KEEPALIVE,
                          bind_address=MQTT_BIND_ADDRESS)
        

    def handle_connect(self, mqttc, userdata, flags, result):
        logger.info("MQTT Broker Connected")

        self.connected = True

        self.mqtt.subscribe(
            "{}/{}/{}".format(MQTT_BASE_TOPIC,
                              MQTT_CONTROL_TOPIC, "#"))
        
        self.mqtt.subscribe(
            "{}/{}/{}".format(MQTT_BASE_TOPIC,
                              MQTT_NOTIFICATIONS_TOPIC, "#"))
        
        self.mqtt.will_set('{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                             MQTT_INTERFACE_TOPIC,
                                             self.__class__.__name__), 
                            'offline', 0, MQTT_RETAIN)

        

        self.publish('{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                            MQTT_INTERFACE_TOPIC,
                                            self.__class__.__name__),
                          'online', 0, MQTT_RETAIN)


    def handle_event(self, raw):
        """Handle Live Event"""
        #logger.debug("Live Event: raw={}".format(
        #    raw))
        

        if MQTT_PUBLISH_RAW_EVENTS:
            self.publish('{}/{}'.format(MQTT_BASE_TOPIC,
                                                MQTT_EVENTS_TOPIC,
                                                MQTT_RAW_TOPIC),
                              json.dumps(raw), 0, MQTT_RETAIN)

    def handle_change(self, raw):
        element, label, property, value = raw 
        """Handle Property Change"""
        #logger.debug("Property Change: element={}, label={}, property={}, value={}".format(
        #    element,
        #    label,
        #    property,
        #    value))

        # Keep track of ARM state
        if element == 'partition':
            if not label in self.partitions:
                self.partitions[label] = dict()

            self.partitions[label][property] = value
        
        if element == 'partition':
            element_topic = MQTT_PARTITION_TOPIC
        elif element == 'zone':
            element_topic = MQTT_ZONE_TOPIC
        elif element == 'output':
            element_topic = MQTT_OUTPUT_TOPIC
        elif element == 'repeater':
            element_topic = MQTT_REPEATER_TOPIC
        elif element == 'bus':
            element_topic = MQTT_BUS_TOPIC
        elif element == 'keypad':
            element_topic = MQTT_KEYPAD_TOPIC
        elif element == 'system':
            element_topic = MQTT_SYSTEM_TOPIC
        elif element == 'user':
            element_topic = MQTT_USER_TOPIC
        else:
            element_topic = element
        
        if MQTT_USE_NUMERIC_STATES:
            publish_value = int(value)
        else:
            publish_value = value
        self.publish('{}/{}/{}/{}/{}'.format(MQTT_BASE_TOPIC,
                                            MQTT_STATES_TOPIC,
                                            element_topic,
                                            label,
                                            property),
                          "{}".format(publish_value), 0, MQTT_RETAIN)

    
    # Utils
    def normalize_mqtt_payload(self, payload):
        payload = payload.decode('utf-8').strip().lower().replace(' ', '_')

        if payload in self.alarm.PGM_ACTIONS or payload in self.alarm.PARTITION_ACTIONS or payload in self.alarm.ZONE_ACTIONS:
            return payload
        elif 'code_toggle' in payload:
            return payload

        return None

    def publish(self, topic, value, qos, retain):
        self.cache[topic] = {'value': value, 'qos': qos, 'retain': retain}
        self.mqtt.publish(topic, value, qos, retain)

    def republish(self):
        for k in list(self.cache.keys()):
            v = self.cache[k]
            self.mqtt.publish(k, v['value'], v['qos'], v['retain'])

