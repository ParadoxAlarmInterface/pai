import json
import logging
import os
import re
import time

from homie.device_base import Device_Base
from homie.node.property.property_contact import Property_Contact
from homie.node.property.property_boolean import Property_Boolean
from homie.node.node_contact import Node_Base


from paradox.event import Event
from paradox.interfaces import Interface
from paradox.interfaces import AsyncQueueInterface
from paradox.lib.utils import SortableTuple, JSONByteEncoder

from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)

from paradox.config import config as cfg

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)

#re_topic_dirty = re.compile(r'[+#/]')
re_topic_dirty = re.compile(r'\W')


def sanitize_topic_part(name):
    return re_topic_dirty.sub('_', name).strip('_')


class HomieMQTTInterface(AsyncQueueInterface):
    """Interface Class using MQTT subscribing to the Homie convention"""
    name = 'mqtt_homie'
    acceptsInitialState = True

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('PAI').getChild(__name__)
        
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
            'topic' : cfg.HOMIE_BASE_TOPIC, 
            'fw_name' : 'python',
            'fw_version' : '0.0.1', 
            'update_interval' : 60,
        }
        
        self.connected = False
        self.cache = dict()
        self.setup_called = False
        self.armed = dict()
        self.node_filter = cfg.HOMIE_NODE_FILTER

    async def run(self):
        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.mqtt.username_pw_set(
                username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        

        required_mappings = 'alarm,arm,arm_stay,arm_sleep,disarm'.split(',')
        if cfg.MQTT_HOMEBRIDGE_ENABLE:
            self.check_config_mappings('MQTT_PARTITION_HOMEBRIDGE_STATES', required_mappings)
        if cfg.MQTT_HOMEASSISTANT_ENABLE:
            self.check_config_mappings('MQTT_PARTITION_HOMEASSISTANT_STATES', required_mappings)
        
        self.alarm_Device = Device_Base(name="paradox",mqtt_settings=self.mqtt_settings,homie_settings=self.homie_settings)
        #self.alarm_Device.topic = 'paradox/homie'
        self.alarm_Device.start()
        last_republish = time.time()
        
        ps.subscribe(self.handle_panel_change, "changes")
        ps.subscribe(self.handle_panel_event, "events")
        ps.subscribe(self.handle_panel_status, "status_update")
        ps.subscribe(self.handle_labels_loaded, "labels_loaded")

        await super().run()

        # while True:
        #     try:
        #         item = self.queue.get()
        #         if item[1] == 'command':
        #             if item[2] == 'stop':
        #                 break
        #         if time.time() - last_republish > cfg.MQTT_REPUBLISH_INTERVAL:
        #             self.republish()
        #             last_republish = time.time()
        #     except Exception:
        #         self.logger.exception("ERROR in MQTT Run loop")


        # if self.connected:
        #     # Need to set as disconnect will delete the last will
        #     self.publish('{}/{}/{}'.format(cfg.HOMIE_BASE_TOPIC,
        #                                cfg.MQTT_INTERFACE_TOPIC,
        #                                self.__class__.__name__),
        #              'offline', 0, retain=True)
        
        #     self.mqtt.disconnect()

        # self.mqtt.loop_stop()

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        self.logger.debug("Stopping MQTT Interface")
        self.queue.put_nowait(SortableTuple((0, 'command', 'stop')))
        self.join()

    def event(self, event: Event):
        """ Enqueues an event"""
        self.queue.put_nowait(SortableTuple((2, 'event', event)))

    def change(self, element, label, panel_property, value):
        """ Enqueues a change """
        self.queue.put_nowait(SortableTuple(
            (2, 'change', (element, label, panel_property, value))))

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
            ps.sendMessage("notifications", message=dict(source=self.name, payload=payload, level=level))
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

                ps.sendMessage('notifications', message=dict(
                    source="mqtt",
                    message="Command by {}: {}".format(
                    cfg.MQTT_TOGGLE_CODES[tokens[1]], command),
                    level=logging.INFO))

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

    def handle_connect(self, mqttc, userdata, flags, result):
        self.logger.info("MQTT Broker Connected")

        self.connected = True
        self.logger.debug(
            "Subscribing to topics in {}/{}".format(cfg.HOMIE_BASE_TOPIC, cfg.MQTT_CONTROL_TOPIC))
        # self.mqtt.subscribe(
        #     "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
        #                       cfg.MQTT_CONTROL_TOPIC, "#"))

        # self.mqtt.subscribe(
        #     "{}/{}/{}".format(cfg.MQTT_BASE_TOPIC,
        #                       cfg.MQTT_NOTIFICATIONS_TOPIC, "#"))

        # self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
        #                                cfg.MQTT_INTERFACE_TOPIC,
        #                                self.__class__.__name__),
        #              'online', 0, retain=True)

    def handle_panel_status(self, status):
        """
        Handle Status Message

        :param raw: object with properties (can have byte properties)
        :return:
        """
        self.logger.info("HOMIE: handling status: %s level: %s" % (1,2))
        #get the element type = eg zone, system, troubles
        for element in status:
            # check element in node filter, which means we might have something to do with it.
            if element in self.node_filter:
                item = status[element]

                #get the cache element to match the status, this is just the key=label
                cacheelement = self.cache[element]
                if type(item) is dict:

                    # here's where the status is different from the cache.
                    for key in item:
                        #zone: 1: {arm=True}
                        #for a zone, the key = 1, 2 etc, needs to be matched to the labels.
                        if type(item[key]) is dict:
                            #get the cached label name which is used to pull the node from teh alarm device
                            if key in cacheelement:
                                cacheitem = cacheelement[key]
                                node = self.alarm_Device.get_node(cacheitem)
                                #check here if the node already has properties.....this means the node_filter has
                                if len(node.properties) == 0:
                                    print("need to add all attrbiutes in the item[key]")
                                    for attribute in item[key]:
                                        value = item[key][attribute]
                                        attribute_sanitised = attribute.replace('_','').lower()
                                        #TODO: need to fix this, it's assuming all properties are boolean
                                        newProperty = Property_Boolean(node,id=attribute_sanitised,data_type='boolean',name=attribute.lower(),value=value)
                                        node.add_property(newProperty)
                                else:
                                    print("Only get the values for teh attributes we care about")
                                    for node_property in node.properties:
                                        value = item[key][node_property]
                                        attribute_sanitised = node_property.replace('_','').lower()
                                        #propertytoupdate = node.get_property(attribute_sanitised)
                                        node.set_property_value(attribute_sanitised.lower(),value)
                                    
                            

                            
                        else:
                        #troubles: timer_loss_trouble=false
                            value = item[key]
                            try:
                                cacheitem = self.cache[element]
                                for node in cacheitem:
                                    if node['index'] == key:
                                        logging.debug("Element %s Label %s value %s" % (element,node['label'], value))
                            except:
                                pass
                else:
                    attribute = element
                    value = element[attribute]
                
                try:
                    cacheitem = self.cache[element]
                except:
                    pass

    def handle_panel_event(self, event):
        """
        Handle Live Event

        :param raw: object with properties (can have byte properties)
        :return:
        """
        self.logger.info("HOMIE: handling event: %s level: %s" % (event.message,event.level))
        # if cfg.MQTT_PUBLISH_RAW_EVENTS:
        #     self.publish('{}/{}'.format(cfg.MQTT_BASE_TOPIC,
        #                                 cfg.MQTT_EVENTS_TOPIC,
        #                                 cfg.MQTT_RAW_TOPIC),
        #                  json.dumps(event.props, ensure_ascii=False, cls=JSONByteEncoder), 0, cfg.MQTT_RETAIN)

    def handle_panel_change(self, change):
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
                    self.publish_dash(cfg.MQTT_DASH_TEMPLATE, list(self.partitions.keys()))

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
        if not self.setup_called: 
            self.cache['{}-{}-{}'.format(change['type'], change['label'], change['property'])] = change
            return
        
        # if element == 'partition':
        #     if cfg.MQTT_HOMEBRIDGE_ENABLE:
        #         self.handle_change_external(element, label, attribute, value, element_topic,
        #                                     cfg.MQTT_PARTITION_HOMEBRIDGE_STATES, cfg.MQTT_HOMEBRIDGE_SUMMARY_TOPIC, 'hb')

        #     if cfg.MQTT_HOMEASSISTANT_ENABLE:
        #         self.handle_change_external(element, label, attribute, value, element_topic,
        #                                     cfg.MQTT_PARTITION_HOMEASSISTANT_STATES, cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC,
        #                                     'hass')

        if element in self.node_filter and attribute in self.node_filter[element]:
            self.logger.info("HOMIE: handling change: element: %s label: %s attribute: %s = %s" % (element,label,attribute,value))
            try:
                label_sanitised = label.replace('_','').lower()
                #Look for the node in the alarm device node list
                if label_sanitised in self.alarm_Device.nodes:
                    #get the node if we know it is there
                    node = self.alarm_Device.get_node(label_sanitised)
                    self.logger.debug("HOMIE: Found existing node for '%s'" % label)
                    #get the current property being changed.  We should have all these from the internal callback
                    currentProperty = node.get_property(attribute.lower())
                    #if currentProperty is None:
                    #    #no property found with that attribute name for that zone
                    #    newProperty = Property_Boolean(node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                    #    node.add_property(newProperty)

                    self.logger.info("HOMIE: Found existing property '%s' for '%s' setting to %s" % (attribute, label, value))
                    #update the found property with the new value.
                    node.set_property_value(attribute.lower(),value)
                #else:  #no node found, add one with the current property.
                #    try:
                #        #NONE OF THIS SHOULD BE NEEDED ANY MORE 2019-09-04
                #        #move contact_node to class, and set each zone as a node.
                #        zone_node = Node_Base(self.alarm_Device,name=label,id=label_sanitised,type_=element)
                #        self.logger.info("HOMIE: Adding new property boolean '%s'" % attribute) 
                #        #node.id = label
                #        newProperty = Property_Boolean(zone_node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                #        zone_node.add_property(newProperty)
                #    
                #        #self.nodes[label] = node
                #        self.alarm_Device.add_node(zone_node)
                #    except Exception as e:
                #        self.logger.error("HOMIE: Error creating node: %s with error: %s" %(zone_node.name, str(e)))
            except Exception as e:
                #has a node so use it.
                self.logger.error("HOMIE: Error updating node: %s with error: %s" %(zone_node.name, str(e)))
            #else:
            #    #needs a new node
            #    self.logger.info("HOMIE: Found existing node for '%s'" % label)
            #    #node = self.get_node(label)
        #elif element == 'system':
        #    self.logger.debug("HOMIE: Status element: " + change['type'])

            #can parse power, vdc, dc and battery under here.

        
        
    def check_config_mappings(self, config_parameter, required_mappings):
        # Check states_map
        keys = getattr(cfg, config_parameter).keys()
        missing_mappings = [k for k in required_mappings if k not in keys]
        if len(missing_mappings):
            logger.warning(', '.join(missing_mappings) + " keys are missing from %s config." % config_parameter)

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
            if attribute in ['alarm', 'strobe_alarm', 'audible_alarm', 'bell_activated', 'silent_alarm'] and self.armed[service][label]['alarm']:
                state = self.armed[service][label]['state']  # Restore the ARM state
                self.armed[service][label]['alarm'] = False  # Reset alarm state

            elif attribute in ['arm_stay', 'arm', 'arm_sleep'] and self.armed[service][label]['attribute'] == attribute:
                state = states_map['disarm']
                self.armed[service][label] = dict(attribute=None, state=None, alarm=False)
            else:
                return  # Do not publish a change

        self.publish('{}/{}/{}/{}/{}'.format(cfg.HOMIE_BASE_TOPIC,
                                             cfg.MQTT_STATES_TOPIC,
                                             element_topic,
                                             sanitize_topic_part(label),
                                             summary_topic),
                     "{}".format(state), 0, cfg.MQTT_RETAIN)

    def handle_internal(self, message):
        self.logger.info("HOMIE: Found internal message: '%s'" % message)


    '''Use this method for receiving communication from the panel.  properties_enumerated is after update all labels'''
    def handle_labels_loaded(self, data):

        # look through each element = eg zone, system, troubles
        for element in data:
            #check if element type in the node filter.
            if element in self.node_filter:
                if element not in self.cache:
                    
                    nodes = dict()
                    self.cache[element] = nodes
                else:
                    nodes = self.cache[element]

                for item, itemdata in data[element].items():
                    
                    #Add node filter on item here

                    #self.nodes[entry['label']].setProperty(entry['property']).send(entry['value'])
                    #element = 'zone' label = 'front_door_reed'
                    #element = system label = 'vdc'
                    label = itemdata['label']
                    key = itemdata['key']
                    id = itemdata['id']
                    
                    

                    label_sanitised = key.replace('_','').lower()
                    zone_node = Node_Base(self.alarm_Device,name=label,id=label_sanitised,type_=element)
                    
                    #update the self.cache, with the index and key map, so it can be used to resolve
                    # a status update on zone[1] = node["front_door_rood"]
                    nodes[id] = label_sanitised

                    #could add the properties here from the node_filter...but need to work out how to add all
                    #when at this point they are not known
                    #maybe if node filter has open, alarm, add those as properties.
                    #if node_filter has "all", don't add properties.
                    #then under update status, if node has no properties, add everything
                    node_filter_attributes = self.node_filter[element]
                    if len(node_filter_attributes) > 1 or node_filter_attributes[0] != 'all':
                        for attribute in node_filter_attributes:
                            #TODO: need to fix this, it's assuming all properties are boolean
                            newProperty = Property_Boolean(zone_node,id=attribute.lower(),data_type='boolean',name=attribute.lower())
                            zone_node.add_property(newProperty)
                    
                    #add teh zone to the alarm device.
                    self.alarm_Device.add_node(zone_node)
                    
                    #if value not in self.node_filter[element]:
                    #    break
                #if element == 'zone' and (attribute == 'open' or attribute == 'alarm'):
                #    if value not in nodes:
                #        itemnode = dict()
                #        itemnode['label'] = label
                #        itemnode['index'] = id
                #        nodes[value] = itemnode
                #    #element = 'zone'
                #    #label = 'Front door reed'
                #    #value = Front_door_reed'
                #    #can be used for creating nodes....not sure where attributes will come from 
                #    # if attribute in self.node_filter[element]:
                #    #     label_sanitised = label.replace('_','').lower()
                #    #     #Look for the node in the alarm device node list
                #    #     if label_sanitised in self.alarm_Device.nodes:
                #    #         self.logger.info("HOMIE: Alarm Attribute Found existing node for '%s'" % label)#

                #    #         #get the node if we know it is there
                #    #         node = self.alarm_Device.get_node(label_sanitised)
                #    #         self.logger.info("HOMIE: Found existing node for '%s'" % label)
                #    #         #get the current property being changed.
                #    #         currentProperty = node.get_property(attribute.lower())
                #    #         if currentProperty is None:
                #    #             #no property found with that attribute name for that zone
                #    #             newProperty = Property_Boolean(node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                #    #             node.add_property(newProperty)
                #    #     else:  #no node found, add one with the current property.
                #    #         try:
                #    #             #move contact_node to class, and set each zone as a node.
                #    #             zone_node = Node_Base(self.alarm_Device,name=label,id=label_sanitised,type_=element)
                #    #             self.logger.info("HOMIE: Adding new property boolean '%s' to node '%s'" % (attribute, label)) 
                #    #             #node.id = label
                #    #             newProperty = Property_Boolean(zone_node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                #    #             zone_node.add_property(newProperty)
                #            
                #    #             #self.nodes[label] = node
                #    #             self.alarm_Device.add_node(zone_node)
                #    #         except Exception as e:
                #    #             self.logger.error("HOMIE: Error creating node: %s with error: %s" %(zone_node.name, str(e)))
        
        #setup completed (end of internal message), so when true. then change events will start updating node values.
        self.setup_called = True
        #cache not needed any more so clar it for memory.
        #self.cache.clear()

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
