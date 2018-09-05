#!/usr/bin/env python
import logging

# Default configuration.
# Do not edit this.  Copy config_sample.py to config.py and edit that.

# Logging
LOGGING_LEVEL_CONSOLE = logging.INFO
LOGGING_LEVEL_FILE = logging.ERROR
LOGGING_FILE = None #or set to file path LOGGING_FILE='/var/log/paradox.log'
LOGGING_DUMP_PACKETS = False
LOGGING_DUMP_MESSAGES = False

# Connection Type
CONNECTION_TYPE = 'Serial'  #Only serial for now

# Serial Connection Details
SERIAL_PORT = '/dev/ttyS1'

# Paradox
KEEP_ALIVE_INTERVAL = 9
ZONES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
USERS = [1, 2, 3, 4]
OUTPUTS = []
PARTITIONS = [1, 2]
LABEL_REFRESH_INTERVAL = 15 * 60
OUTPUT_PULSE_DURATION = 1
PARTITIONS_CHANGE_NOTIFICATION_IGNORE=['arm_full', 'exit_delay']
POWER_UPDATE_INTERVAL = 60
STATUS_REQUESTS = [1, 2, 3, 5] #4 ignored

# MQTT
MQTT_HOST = 'localhost'
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
MQTT_USERNAME = None
MQTT_PASSWORD = None
MQTT_RETAIN = True
MQTT_BIND_ADDRESS = ''
MQTT_REPUBLISH_INTERVAL = 60 * 60 * 12

# MQTT Topics
MQTT_BASE_TOPIC = 'paradox'
MQTT_ZONE_TOPIC = 'zones'
MQTT_PARTITION_TOPIC = 'partitions'
MQTT_BUS_TOPIC = 'buses'
MQTT_PANEL_TOPIC = 'panels'
MQTT_REPEATER_TOPIC = 'panels'
MQTT_EVENTS_TOPIC = 'events'
MQTT_CONTROL_TOPIC = 'control'
MQTT_OUTPUT_TOPIC = 'outputs'
MQTT_STATES_TOPIC = 'states'
MQTT_RAW_TOPIC = 'raw'
MQTT_NOTIFICATIONS_TOPIC = 'notifications'
MQTT_PUBLISH_RAW_EVENTS = True
MQTT_INTERFACE_TOPIC = 'interface'
MQTT_TOGGLE_CODES = {}

# Pushbullet
PUSHBULLET_KEY = ''
PUSHBULLET_SECRET = ''
PUSHBULLET_CONTACTS = [] # PB User identifiers for notifications

# Signal
SIGNAL_CONTACTS = []
SIGNAL_IGNORE_EVENTS = [] # List of tuples (major, minor)

# GSM
GSM_MODEM_BAUDRATE = 115200
GSM_MODEM_PORT = ''
GSM_CONTACTS = []
GSM_IGNORE_EVENTS = [] # List of tuples (major, minor)


