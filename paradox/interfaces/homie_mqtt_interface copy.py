import homie
import time
import logging
import json
import os
import re

from homie.device_base import Device_Base
from homie.node.property.property_contact import Property_Contact
from homie.node.property.property_boolean import Property_Boolean
from homie.node.node_contact import Node_Base

from paradox.lib.utils import SortableTuple, JSONByteEncoder
from paradox.interfaces import Interface
from paradox.lib import ps

from paradox.config import config as cfg

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)

#re_topic_dirty = re.compile(r'[+#/]')
re_topic_dirty = re.compile(r'\W')



def sanitize_topic_part(name):
    return re_topic_dirty.sub('_', name).strip('_')


class HomieMQTTInterface-O(Interface):
    """Interface Class using Homie to publish MQTT"""
    name = 'mqtt'
    acceptsInitialState = True
    

    def __init__(self):
        super().__init__()
        
        self.logger = logging.getLogger('PAI').getChild(__name__)
        self.connected = False

        self.cache = dict()

        self.armed = dict()

        

        #self.nodes = {}

        self.mqtt_settings = {}

        #self.homie_settings = {}

    def run(self):
        self.mqtt_settings = {
            'MQTT_BROKER' : cfg.MQTT_HOST,
            'MQTT_PORT' : cfg.MQTT_PORT,
            'MQTT_KEEPALIVE' : cfg.MQTT_KEEPALIVE,
            'MQTT_CLIENT_ID' : "paradox_mqtt/{}".format(os.urandom(8).hex()),
            'MQTT_USERNAME': '',
            'MQTT_PASSWORD': '',
            'MQTT_SHARE_CLIENT': True,

        }

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.mqtt_settings['MQTT_USERNAME'] = cfg.MQTT_USERNAME
            self.mqtt_settings['MQTT_PASSWORD'] = cfg.MQTT_PASSWORD
        

        self.homie_settings = {
            'version' : '0.0.1',
            'topic' : 'paradox/homie', 
            'fw_name' : 'python',
            'fw_version' : '0.0.1', 
            'update_interval' : 60,
        }
        self.alarm_Device = Device_Base(name="paradox",mqtt_settings=self.mqtt_settings,homie_settings=self.homie_settings)
        self.alarm_Device.topic = 'paradox/homie'
        self.alarm_Device.start()
        last_republish = time.time()

        ps.subscribe(self.handle_panel_change, "changes")
        ps.subscribe(self.handle_panel_event, "events")
        #ps.subscribe(self.handle_panel_event, "labels_loaded")


        while True:
            try:
                item = self.queue.get()
                if item[1] == 'change':
                    self.handle_change(item[2])
                elif item[1] == 'event':
                    self.handle_event(item[2])
                elif item[1] == 'command':
                    if item[2] == 'stop':
                        break
                elif item[1] == 'notify':
                    self.handle_notify(item[2])
                elif item[1] == 'labels_loaded':
                    self.logger.debug("Labels loaded")
                if time.time() - last_republish > cfg.MQTT_REPUBLISH_INTERVAL:
                    self.republish()
                    last_republish = time.time()
            except Exception as e:
                self.logger.exception("ERROR in MQTT Run loop")

        if self.connected:
            #self.mqtt.disconnect()
            time.sleep(0.5)

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        #self.mqtt.disconnect()
        self.logger.debug("Stopping Homie MQTT Interface")
        self.queue.put_nowait(SortableTuple((0, 'command', 'stop')))
        #self.mqtt.loop_stop()
        self.join()

    def event(self, raw):
        """ Enqueues an event"""
        self.queue.put_nowait(SortableTuple((2, 'event', raw)))

    def change(self, element, label, property, value):
        """ Enqueues a change """
        self.queue.put_nowait(SortableTuple(
            (2, 'change', (element, label, property, value))))

    def notify(self, source, message, level):
        self.queue.put_nowait(SortableTuple((2, 'notify', (source, message, level))))

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

            if command in cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS and cfg.MQTT_HOMEBRIDGE_ENABLE:
                command = cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS[command]
            elif command in cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS and cfg.MQTT_HOMEASSISTANT_ENABLE:
                command = cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS[command]

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

    # def handle_disconnect(self, mqttc, userdata, rc):
    #     self.logger.info("MQTT Broker Disconnected")
    #     self.connected = False

    #     time.sleep(1)

    #     #if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
    #         #self.mqtt.username_pw_set(
    #         #    username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

    #     #self.mqtt.connect(host=cfg.MQTT_HOST,
    #     #                  port=cfg.MQTT_PORT,
    #     #                  keepalive=cfg.MQTT_KEEPALIVE,
    #     #                  bind_address=cfg.MQTT_BIND_ADDRESS)

    # def handle_connect(self, mqttc, userdata, flags, result):
    #     self.logger.info("MQTT Broker Connected")

    #     self.connected = True
    #     self.logger.debug(
    #         "Subscribing to topics in {}/{}".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC))
    #     #self.mqtt.subscribe(
    #     #    "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
    #     #                      cfg.MQTT_CONTROL_TOPIC, "#"))

    #     #self.mqtt.subscribe(
    #     #    "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
    #     #                      cfg.MQTT_NOTIFICATIONS_TOPIC, "#"))

    #     #self.mqtt.will_set('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
    #     #                                     cfg.MQTT_INTERFACE_TOPIC,
    #     #                                     self.__class__.__name__),
    #     #                   'offline', 0, cfg.MQTT_RETAIN)

    #     #self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
    #     #                               cfg.MQTT_INTERFACE_TOPIC,
    #     #                               self.__class__.__name__),
    #     #             'online', 0, cfg.MQTT_RETAIN)

    def handle_event(self, raw):
        """
        Handle Live Event

        :param raw: object with properties (can have byte properties)
        :return:
        """
        #self.logger.debug("HOMIE: handling event: %s" % raw.props)
        self.logger.info("HOMIE: handling event: %s level: %s" % (raw.message,raw.level))
        #if cfg.MQTT_PUBLISH_RAW_EVENTS:
        #    self.publish('{}/{}'.format(cfg.MQTT_BASE_TOPIC,
        #                                cfg.MQTT_EVENTS_TOPIC,
        #                                cfg.MQTT_RAW_TOPIC),
        #                 json.dumps(raw.props, ensure_ascii=False, cls=JSONByteEncoder), 0, cfg.MQTT_RETAIN)

    def handle_notify(self, raw):
        sender, message, level = raw

        self.logger.debug(level, "sender: %s, message: %s" % (sender, message))
        

    def handle_panel_change(self, raw):
        element, label, attribute, value = raw
        """Handle Property Change"""
        
        
        # Keep track of ARM state
        if element == 'partition':
            if label not in self.partitions:
                self.partitions[label] = dict()

                # After we get 2 partitions, lets publish a dashboard
                #if cfg.MQTT_DASH_PUBLISH and len(self.partitions) == 2:
                #    self.publish_dash(cfg.MQTT_DASH_TEMPLATE, list(self.partitions.keys()))

            self.partitions[label][attribute] = value

        if element in ELEMENT_TOPIC_MAP:
            element_topic = ELEMENT_TOPIC_MAP[element]
        else:
            element_topic = element

        if cfg.MQTT_USE_NUMERIC_STATES:
            publish_value = int(value)
        else:
            publish_value = value

        #self.publish('{}/{}/{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
        #                                     cfg.MQTT_STATES_TOPIC,
        #                                     element_topic,
        #                                     sanitize_topic_part(label),
        #                                     attribute),
        #             "{}".format(publish_value), 0, cfg.MQTT_RETAIN)

        if element == 'partition':
            if cfg.MQTT_HOMEBRIDGE_ENABLE:
                self.handle_change_external(element, label, attribute, value, element_topic,
                                            cfg.MQTT_PARTITION_HOMEBRIDGE_STATES, cfg.MQTT_HOMEBRIDGE_SUMMARY_TOPIC, 'hb')

            if cfg.MQTT_HOMEASSISTANT_ENABLE:
                self.handle_change_external(element, label, attribute, value, element_topic,
                                            cfg.MQTT_PARTITION_HOMEASSISTANT_STATES, cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC,
                                            'hass')
        
        if element == 'zone' and (attribute == "open"): #or attribute == "alarm"):
            self.logger.info("HOMIE: handling change: element: %s label: %s attribute: %s = %s" % (element,label,attribute,value))
            try:
                label_sanitised = label.replace('_','').lower()
                node = self.alarm_Device.get_node(label_sanitised)
                self.logger.info("HOMIE: Found existing node for '%s'" % label)
                currentProperty = node.get_property(attribute.lower())
                self.logger.info("HOMIE: Found existing property '%s' setting to %s" % (attribute, value))
                currentProperty = value
                #if value:
                #    self.logger.info("HOMIE: Setting property to OPEN")
                #    #node.set_property_value(attribute.lower(),"OPEN")
                #   currentProperty = "OPEN"
                #else:
                #    self.logger.info("HOMIE: Setting property to OPEN")
                #    currentProperty = "CLOSED"
                currentProperty = node.get_property(attribute.lower())
                self.logger.info("HOMIE: Current property setting '%s'" % currentProperty)
            except Exception as e:
                #has a node so use it.
                self.logger.info("HOMIE: Adding new contact node for '%s'" % label) 
                try:
                    #move contact_node to class, and set each zone as a node.
                    zone_node = Node_Base(self.alarm_Device,name=label,id=label_sanitised,type_=element)
                    self.logger.info("HOMIE: Adding new property boolean '%s'" % attribute) 
                    #node.id = label
                    newProperty = Property_Boolean(zone_node,id=attribute.lower(),name=attribute.lower(),value=value)
                    zone_node.add_property(newProperty)
                    
                    
                    #self.nodes[label] = node
                    self.alarm_Device.add_node(zone_node)
                except Exception as e:
                    self.logger.error("HOMIE: Error creating node: %s with error: %s" %(zone_node.name, str(e)))
            #else:
            #    #needs a new node
            #    self.logger.info("HOMIE: Found existing node for '%s'" % label)
            #    #node = self.get_node(label)

    def validate_id(self,id):
        if isinstance(id, str):
            r = re.compile(r'(^(?!\-)[a-z0-9\-]+(?<!\-)$)')
            return id if r.match(id) else False

    def handle_change_external(self, element, label, attribute,
                               value, element_topic, states_map,
                               summary_topic, service):

        if service not in self.armed:
            self.armed[service] = dict()

        if label not in self.armed[service]:
            self.armed[service][label] = dict(attribute=None, state=None, alarm=False)

        # Property changing to True: Alarm or arm
        if value:
            if attribute in ['alarm', 'bell_activated', 'strobe_alarm', 'silent_alarm', 'audible_alarm'] and not self.armed[service][label]['alarm']:
                state = states_map['alarm']
                self.armed[service][label]['alarm'] = True

            # only process if not armed already
            elif self.armed[service][label]['attribute'] is None:
                if attribute == 'stay_arm':
                    state = states_map['stay_arm']
                elif attribute == 'arm':
                    state = states_map['arm']
                elif attribute == 'sleep_arm':
                    state = states_map['sleep_arm']
                else:
                    return

                self.armed[service][label]['attribute'] = attribute
                self.armed[service][label]['state'] = state
            else:
                return  # Do not publish a change

        # Property changing to False: Disarm or alarm stop
        else:
            # Alarm stopped
            if attribute in ['alarm', 'strobe_alarm', 'audible_alarm', 'bell_activated', 'silent_alarm'] and self.armed[service][label]['alarm']:
                state = self.armed[service][label]['state']  # Restore the ARM state
                self.armed[service][label]['alarm'] = False  # Reset alarm state

            elif attribute in ['stay_arm', 'arm', 'sleep_arm'] and self.armed[service][label]['attribute'] == attribute:
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

    #def handle_advertise_item(self, raw):
    #    item = raw
    #    """handle each item"""

    def publish(self, topic, value, qos, retain):
        self.cache[topic] = {'value': value, 'qos': qos, 'retain': retain}
        #self.mqtt.publish(topic, value, qos, retain)

    def republish(self):
        for k in list(self.cache.keys()):
            v = self.cache[k]
            #self.mqtt.publish(k, v['value'], v['qos'], v['retain'])

    def publish_dash(self, fname, partitions):
        if len(partitions) < 2:
            return

        if os.path.exists(fname):
            with open(fname, 'r') as f:
                data = f.read()
                data = data.replace('__PARTITION1__', partitions[0]).replace('__PARTITION2__', partitions[1])
                #self.mqtt.publish(cfg.MQTT_DASH_TOPIC, data, 2, True)
                self.logger.info("MQTT Dash panel published to {}".format(cfg.MQTT_DASH_TOPIC))
        else:
            self.logger.warn("MQTT DASH Template not found: {}".format(fname))
