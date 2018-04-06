#!/usr/bin/env python
import logging

# Default configuration.
# Do not edit this.  Copy config_sample.py to config.py and edit that.

# Logging
LOGGING_LEVEL_CONSOLE = logging.INFO
LOGGING_LEVEL_FILE = logging.ERROR
LOGGING_FILE = None #or set to file path LOGGING_FILE='/var/log/paradox.log'

# Connection Type
CONNECTION_TYPE = 'Serial'  #Only serial for now

# Serial Connection Details
SERIAL_PORT = '/dev/ttyS1'

# Paradox
KEEP_ALIVE_INTERVAL = 9
ZONES = 32
USERS = 32
OUTPUTS = 16
PARTITIONS = 2
LABEL_REFRESH_INTERVAL = 15 * 60
OUTPUT_PULSE_DURATION = 1

# MQTT
MQTT_HOST = 'localhost'
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
MQTT_USERNAME = None
MQTT_PASSWROD = None

# MQTT Topics
MQTT_BASE_TOPIC = 'paradox'
MQTT_ZONE_TOPIC = 'zones'
MQTT_PARTITION_TOPIC = 'partitions'
MQTT_EVENTS_TOPIC = 'events'
MQTT_CONTROL_TOPIC = 'control'
MQTT_OUTPUT_TOPIC = 'outputs'
MQTT_STATES_TOPIC = 'states'
MQTT_RAW_TOPIC = 'raw'
