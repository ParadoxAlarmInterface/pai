import logging
import os

import typing
from collections import namedtuple

from .core import AbstractMQTTInterface, sanitize_topic_part, ELEMENT_TOPIC_MAP

from paradox.config import config as cfg
from paradox.lib import ps

from homie.device_base import Device_Base
from homie.node.property.property_contact import Property_Contact
from homie.node.property.property_boolean import Property_Boolean
from homie.node.node_contact import Node_Base

logger = logging.getLogger('PAI').getChild(__name__)

PreparseResponse = namedtuple('preparse_response', 'topics element content')


class HomieMQTTInterface2(AbstractMQTTInterface):
    name = "homie_mqtt"

    def __init__(self):
        super().__init__()
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
        #self.alarm_Device.start()

        ps.subscribe(self.handle_panel_change, "changes")
        #ps.subscribe(self.handle_panel_event, "events")
        ps.subscribe(self.handle_status_update, "status_update")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")

        await super().run()

    def on_connect(self, client, userdata, flags, result):
        super().on_connect(client, userdata, flags, result)
        logger.debug("On Connect")
        

    def handle_status_update(self, status):
        for thing in status:
            logger.debug("Status thing:" + thing)

    def handle_labels_loaded(self, data):
        logger.debug("Status thing:" + data)

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

        #if not self.setup_called: 
        #    self.cache['{}-{}-{}'.format(change['type'], change['label'], change['property'])] = change
        #    return

        if element in self.node_filter and attribute in self.node_filter[element]:
            logger.info("HOMIE: handling change: element: %s label: %s attribute: %s = %s" % (element,label,attribute,value))
            try:
                label_sanitised = label.replace('_','').lower()
                #Look for the node in the alarm device node list
                if label_sanitised in self.alarm_Device.nodes:
                    #get the node if we know it is there
                    node = self.alarm_Device.get_node(label_sanitised)
                    logger.debug("HOMIE: Found existing node for '%s'" % label)
                    #get the current property being changed.  We should have all these from the internal callback
                    currentProperty = node.get_property(attribute.lower())
                    #if currentProperty is None:
                    #    #no property found with that attribute name for that zone
                    #    newProperty = Property_Boolean(node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                    #    node.add_property(newProperty)

                    logger.info("HOMIE: Found existing property '%s' for '%s' setting to %s" % (attribute, label, value))
                    #update the found property with the new value.
                    node.set_property_value(attribute.lower(),value)
                #else:  #no node found, add one with the current property.
                #    try:
                #        #NONE OF THIS SHOULD BE NEEDED ANY MORE 2019-09-04
                #        #move contact_node to class, and set each zone as a node.
                #        zone_node = Node_Base(self.alarm_Device,name=label,id=label_sanitised,type_=element)
                #        logger.info("HOMIE: Adding new property boolean '%s'" % attribute) 
                #        #node.id = label
                #        newProperty = Property_Boolean(zone_node,id=attribute.lower(),data_type='boolean',name=attribute.lower(),value=value)
                #        zone_node.add_property(newProperty)
                #    
                #        #self.nodes[label] = node
                #        self.alarm_Device.add_node(zone_node)
                #    except Exception as e:
                #        logger.error("HOMIE: Error creating node: %s with error: %s" %(zone_node.name, str(e)))
            except Exception as e:
                #has a node so use it.
                logger.error("HOMIE: Error updating node: %s with error: %s" %(zone_node.name, str(e)))
            #else:
            #    #needs a new node
            #    logger.info("HOMIE: Found existing node for '%s'" % label)
            #    #node = self.get_node(label)
        #elif element == 'system':
        #    logger.debug("HOMIE: Status element: " + change['type'])

            #can parse power, vdc, dc and battery under here.    
