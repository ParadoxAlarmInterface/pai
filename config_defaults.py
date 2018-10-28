#!/usr/bin/env python
import logging

# Default configuration.
# Do not edit this.  Copy config_sample.py to config.py and edit that.

# Logging
LOGGING_LEVEL_CONSOLE = logging.INFO # See documentation of Logging package
LOGGING_LEVEL_FILE = logging.ERROR
LOGGING_FILE = None             	# or set to file path LOGGING_FILE='/var/log/paradox.log'
LOGGING_DUMP_PACKETS = False    	# Dump RAW Packets to log
LOGGING_DUMP_MESSAGES = False   	# Dump Messages to log

# Connection Type
CONNECTION_TYPE = 'Serial'  		# Serial or IP

# Serial Connection Details
SERIAL_PORT = '/dev/ttyS1' 		# Pathname of the Serial Port

# IP Connection Defails
IP_CONNECTION_HOST = '127.0.0.1'	# IP Module address when using direct IP Connection
IP_CONNECTION_PORT = 10000		# IP Module port when using direct IP Connection
IP_CONNECTION_PASSWORD = b'0000' 	# IP Module password
IP_CONNECTION_SITEID = None 		# SITE ID. IF defined, connection will be made through this method.
IP_CONNECTION_EMAIL = None 		# Email registered in the site

# Paradox
KEEP_ALIVE_INTERVAL = 9     		# Interval between status updates
ZONES = range(1, 17)			# Zones to monitor and control
USERS = [1, 2, 3, 4]   			# Users to consider
OUTPUTS = range(1, 17)  		# Outputs to monitor and control
PARTITIONS = [1, 2]     		# Partitions to monitor and control
BUSES = range(1, 17)			# Buses to monitor
REPEATERS = range(1, 9)			# Repeaters to monitor
KEYPADS = range(1, 9)			# Keypads to monitor
LABEL_REFRESH_INTERVAL = 15 * 60        # Interval between refresh of labels
OUTPUT_PULSE_DURATION = 1               # Duration of a PGM pulse in seconds
PARTITIONS_CHANGE_NOTIFICATION_IGNORE = ['arm_full', 'exit_delay'] # Do not send notifications for these notificions
STATUS_REQUESTS = [0, 1, 2, 3, 4, 5]
SYNC_TIME = True    			# Update panel time
PASSWORD = b'0000'   			# PC Password

POWER_UPDATE_INTERVAL = 60      	# Interval between updates of the battery, DC and VDC voltages
PUSH_POWER_UPDATE_WITHOUT_CHANGE = True # Always notify interfaces of power changes
PUSH_UPDATE_WITHOUT_CHANGE = False      # Always notify interfaces of all changes

# MQTT
MQTT_ENABLE = False			# Enable MQTT Interface
MQTT_HOST = 'localhost' 		# Hostname or address
MQTT_PORT = 1883        		# TCP Port
MQTT_KEEPALIVE = 60     		# Keep alive
MQTT_USERNAME = None    		# MQTT Username for authentication
MQTT_PASSWORD = None    		# MQTT Password
MQTT_RETAIN = True      		# Publish messages with Retain
MQTT_BIND_ADDRESS = ''
MQTT_REPUBLISH_INTERVAL = 60 * 60 * 12  # Interval for republishing all data
MQTT_HOMEBRIDGE_ENABLE = False

# MQTT Topics
MQTT_BASE_TOPIC = 'paradox'             # Root of all topics
MQTT_ZONE_TOPIC = 'zones'               # Base for zone states
MQTT_PARTITION_TOPIC = 'partitions'     # Base for partition states
MQTT_BUS_TOPIC = 'buses'                # Base for buses states
MQTT_SYSTEM_TOPIC = 'system'            # Base for panel states
MQTT_REPEATER_TOPIC = 'repeaters'       # Base for repeater states      
MQTT_EVENTS_TOPIC = 'events'            # Base for events
MQTT_CONTROL_TOPIC = 'control'          # Base for control of othe elements (ROOT/CONTROL/TYPE)
MQTT_OUTPUT_TOPIC = 'outputs'
MQTT_KEYPAD_TOPIC = 'keypads'
MQTT_STATES_TOPIC = 'states'
MQTT_RAW_TOPIC = 'raw'
MQTT_SUMMARY_TOPIC = 'current'
MQTT_NOTIFICATIONS_TOPIC = 'notifications'
MQTT_PUBLISH_RAW_EVENTS = True
MQTT_INTERFACE_TOPIC = 'interface'
MQTT_TOGGLE_CODES = {}
MQTT_USE_NUMERIC_STATES = False         # use 0 and 1 instead of True and False

# Pushbullet
PUSHBULLET_ENABLE = False
PUSHBULLET_KEY = ''                     # Authentication key used for Pushbullet
PUSHBULLET_SECRET = ''                  # Authentication secret used for Pushbullet
PUSHBULLET_CONTACTS = []                # Pushbullet user identifiers for notifications and interaction

# Signal
SIGNAL_ENABLE = False
SIGNAL_CONTACTS = []                    # Contacts that are allowed to control the panel and receive notifications through Signal
SIGNAL_IGNORE_EVENTS = []               # List of tuples (major, minor)

# GSM
GSM_ENABLE = False
GSM_MODEM_BAUDRATE = 115200             # Baudrate of the GSM modem
GSM_MODEM_PORT = ''                     # Pathname of the serial port
GSM_CONTACTS = []                       # Contacts that are allowed to control the panel and receive notifications through SMS
GSM_IGNORE_EVENTS = []                  # List of tuples [(major, minor), ...]

# IP Socket Interface
IP_INTERFACE_ENABLE = False
IP_INTERFACE_BIND_ADDRESS = '0.0.0.0'
IP_INTERFACE_BIND_PORT = 10000
IP_INTERFACE_PASSWORD = b'0000'

