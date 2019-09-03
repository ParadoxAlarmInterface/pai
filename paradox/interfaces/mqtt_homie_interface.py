import json
import logging
import os
import re
import time
import types
import homie

from paradox.event import Event
from paradox.interfaces import Interface

from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)

from paradox.config import config as cfg

class MQTTHomieInterface(Interface):
    """Interface Class using MQTT and the Homie convention"""
    name = 'mqtt_homie'
    acceptsInitialState = True

    def __init__(self):
        super().__init__()
        
        self.homie_config = {
            'HOST': cfg.MQTT_HOST,
            'PORT': cfg.MQTT_PORT,
            'KEEPALIVE': cfg.MQTT_KEEPALIVE,
            'USERNAME': cfg.MQTT_USERNAME,
            'PASSWORD': cfg.MQTT_PASSWORD,
            'CA_CERTS': '',
            'DEVICE_ID': 'homie',
            'DEVICE_NAME': 'paradox',
            'TOPIC': cfg.MQTT_BASE_TOPIC}
        
        self.nodes = {}
        self.cache = {}
        self.setup_called = False

    def start(self):
        ps.subscribe(self.change, "changes")
        ps.subscribe(self.event, "events")
        ps.subscribe(self.internal, "internal")

        self.homie = homie.Homie(self.homie_config)
        self.nodes['events'] = self.homie.Node('event', 'event')
        self.nodes['events'].advertise('last')

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        logger.debug("Stopping MQTT Homie Interface")

    def event(self, event: Event):
        """ Enqueues an event"""
        self.nodes['events'].setProperty('last').send(str(event))

    def internal(self, message):
        if message == "properties_enumerated":
            
            self.homie.setup()
            for k in self.cache:
                entry = self.cache[k]
                self.nodes[entry['label']].setProperty(entry['property']).send(entry['value'])
            
            self.setup_called = True

    def change(self, change):
        change['property'] = change['property'].replace('_','-')

        """ Enqueues a change """
        if change['label'] not in self.nodes:
            node = self.homie.Node(change['label'], change['type'])
            self.nodes[change['label']] = node
        else:
            node = self.nodes[change['label']]

        if change['property'] not in self.nodes[change['label']].properties:
            node.advertise(change['property'])
        
        if isinstance(change['value'], bool):
            change['value'] = str(change['value'])
    
        if self.setup_called: 
            node.setProperty(change['property']).send(change['value'])
        else:
            self.cache['{}-{}-{}'.format(change['type'], change['label'], change['property'])] = change
