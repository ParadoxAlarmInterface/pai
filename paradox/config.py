import os
import logging


class Config:

    DEFAULTS = { 
        "LOGGING_LEVEL_CONSOLE": logging.INFO,  # See documentation of Logging package
        "LOGGING_LEVEL_FILE": logging.ERROR,
        "LOGGING_FILE": '/var/log/paradox.log',  # or set to file path LOGGING_FILE:'/var/log/paradox.log'
        "LOGGING_DUMP_PACKETS": False,          # Dump RAW Packets to log
        "LOGGING_DUMP_MESSAGES": False,         # Dump Messages to log
        "LOGGING_DUMP_STATUS": False,           # Dump Status to log

        # Development
        "DEVELOPMENT_DUMP_MEMORY": False,

        # Connection Type
        "CONNECTION_TYPE": 'Serial',          # Serial or IP

        # Serial Connection Details
        "SERIAL_PORT": '/dev/ttyS1',         # Pathname of the Serial Port

        # IP Connection Defails
        "IP_CONNECTION_HOST": '127.0.0.1',    # IP Module address when using direct IP Connection
        "IP_CONNECTION_PORT": 10000,          # IP Module port when using direct IP Connection
        "IP_CONNECTION_PASSWORD": b'0000',    # IP Module password
        "IP_CONNECTION_SITEID": None,         # SITE ID. IF defined, connection will be made through this method.
        "IP_CONNECTION_EMAIL": None,          # Email registered in the site

        # Paradox
        "KEEP_ALIVE_INTERVAL": 10,        # Interval between status updates

        "LIMITS": {},  # By default all zones will be monitored

        "LABEL_REFRESH_INTERVAL": (15 * 60),        # Interval between refresh of labels
        "OUTPUT_PULSE_DURATION": 1,               # Duration of a PGM pulse in seconds
        "PARTITIONS_CHANGE_NOTIFICATION_IGNORE": ['arm_full', 'exit_delay'],  # Do not send notifications for these notificions
        "STATUS_REQUESTS": [0, 1, 2, 3, 4, 5],
        "SYNC_TIME": True,                # Update panel time
        "PASSWORD": None,                 # PC Password. Set to None if Panel has no Password

        "POWER_UPDATE_INTERVAL": 60,               # Interval between updates of the battery, DC and VDC voltages
        "PUSH_POWER_UPDATE_WITHOUT_CHANGE": True,  # Always notify interfaces of power changes
        "PUSH_UPDATE_WITHOUT_CHANGE": False,       # Always notify interfaces of all changes

        # MQTT
        "MQTT_ENABLE": False,             # Enable MQTT Interface
        "MQTT_HOST": 'localhost',         # Hostname or address
        "MQTT_PORT": 1883,                # TCP Port
        "MQTT_KEEPALIVE": 60,             # Keep alive
        "MQTT_USERNAME": None,            # MQTT Username for authentication
        "MQTT_PASSWORD": None,            # MQTT Password
        "MQTT_RETAIN": True,              # Publish messages with Retain
        "MQTT_BIND_ADDRESS": '127.0.0.1',
        "MQTT_REPUBLISH_INTERVAL": 60 * 60 * 12,  # Interval for republishing all data
        "MQTT_HOMEBRIDGE_ENABLE": False,
        "MQTT_HOMEASSISTANT_ENABLE": False,

        # MQTT Topics
        "MQTT_BASE_TOPIC": 'paradox',             # Root of all topics
        "MQTT_ZONE_TOPIC": 'zones',               # Base for zone states
        "MQTT_PARTITION_TOPIC": 'partitions',     # Base for partition states
        "MQTT_BUS_TOPIC": 'buses',                # Base for buses states
        "MQTT_SYSTEM_TOPIC": 'system',            # Base for panel states
        "MQTT_REPEATER_TOPIC": 'repeaters',       # Base for repeater states
        "MQTT_USER_TOPIC": 'users',               # Base for user states
        "MQTT_EVENTS_TOPIC": 'events',            # Base for events
        "MQTT_CONTROL_TOPIC": 'control',          # Base for control of othe elements (ROOT/CONTROL/TYPE)
        "MQTT_OUTPUT_TOPIC": 'outputs',
        "MQTT_KEYPAD_TOPIC": 'keypads',
        "MQTT_STATES_TOPIC": 'states',
        "MQTT_RAW_TOPIC": 'raw',
        "MQTT_HOMEBRIDGE_SUMMARY_TOPIC": 'current',
        "MQTT_PARTITION_HOMEBRIDGE_COMMANDS":{
            'STAY_ARM': 'arm_stay',
            'AWAY_ARM': 'arm',
            'NIGHT_ARM': 'arm_sleep',
            'DISARM': 'disarm'},
        "MQTT_PARTITION_HOMEBRIDGE_STATES":{
            'alarm': 'ALARM_TRIGGERED',
            'stay_arm': 'STAY_ARM',
            'arm': 'AWAY_ARM',
            'sleep_arm': 'NIGHT_ARM',
            'disarm': 'DISARMED'},
        "MQTT_HOMEASSISTANT_SUMMARY_TOPIC": 'current_hass',
        "MQTT_PARTITION_HOMEASSISTANT_STATES": {
            'alarm': 'triggered', 
            'stay_arm': 'armed_home',
            'arm': 'armed_away',
            'sleep_arm': 'armed_sleep',
            'disarm': 'disarmed'},
        "MQTT_PARTITION_HOMEASSISTANT_COMMANDS": {
            'armed_home': 'arm_stay', 
            'armed_away': 'arm',
            'armed_sleep': 'arm_sleep',
            'disarmed': 'disarm'},
        "MQTT_NOTIFICATIONS_TOPIC": 'notifications',
        "MQTT_PUBLISH_RAW_EVENTS": True,
        "MQTT_INTERFACE_TOPIC": 'interface',
        "MQTT_TOGGLE_CODES": {},
        "MQTT_USE_NUMERIC_STATES": False,         # use 0 and 1 instead of True and False
        "MQTT_DASH_PUBLISH": False,
        "MQTT_DASH_TOPIC": "metrics/exchange/pai",
        "MQTT_DASH_TEMPLATE": "/etc/pai/mqtt_dash.txt",

        # Interfaces
        "COMMAND_ALIAS": {                       # alias for commands through text based interfaces
            'arm': 'partition all arm',
            'disarm': 'partition all disarm'
        },

        # Pushbullet
        "PUSHBULLET_ENABLE": False,
        "PUSHBULLET_KEY": '',                     # Authentication key used for Pushbullet
        "PUSHBULLET_SECRET": '',                  # Authentication secret used for Pushbullet
        "PUSHBULLET_CONTACTS": [],                # Pushbullet user identifiers for notifications and interaction

        # Pushover
        "PUSHOVER_ENABLE": False,
        "PUSHOVER_KEY": '',                       # Application token for Pushover
        "PUSHOVER_BROADCAST_KEYS": {             # Pushover user or group keys to broadcast notifications to
            #    '<user_key>': '*'                  # value can be '*' or comma separated list of device names
        },

        # Signal
        "SIGNAL_ENABLE": False,
        "SIGNAL_CONTACTS": [],                    # Contacts that are allowed to control the panel and receive notifications through Signal
        "SIGNAL_IGNORE_EVENTS": [],              # List of tuples (major, minor)

        # GSM
        "GSM_ENABLE": False,
        "GSM_MODEM_BAUDRATE": 115200,             # Baudrate of the GSM modem
        "GSM_MODEM_PORT": '',                     # Pathname of the serial port
        "GSM_CONTACTS": [],                       # Contacts that are allowed to control the panel and receive notifications through SMS
        "GSM_IGNORE_EVENTS": [],                  # List of tuples [(major, minor), ...]

        # IP Socket Interface
        "IP_INTERFACE_ENABLE": False,
        "IP_INTERFACE_BIND_ADDRESS": '0.0.0.0',
        "IP_INTERFACE_BIND_PORT": 10000,
        "IP_INTERFACE_PASSWORD": b'0000',

        # Dummy Interface for testing
        "DUMMY_INTERFACE_ENABLE": False,
    }

    CONFIG_LOADED = False
    CONFIG_FILE_LOCATION = None,

    def __init__(self):
        if Config.CONFIG_LOADED:
            return
        self.load()

    def load(self, alt_locations=None):
        Config.CONFIG_LOADED = False

        if alt_locations is not None:
            locations = alt_locations
        else:
            locations = ['/etc/pai/pai.conf',
                         '/usr/local/etc/pai/pai.conf',
                         '~/.local/etc/pai.conf']

        for location in locations:
            location = os.path.expanduser(location)
            if os.path.exists(location) and os.path.isfile(location):
                Config.CONFIG_FILE_LOCATION = location
                break
        else:
            raise(Exception("ERROR: Could not find configuration file. Tried: {}".format(locations)))

        entries = {}
        with open(location) as f:
            exec(f.read(), None, entries)

        # Reset defaults
        for k, v in Config.DEFAULTS.items():
            setattr(Config, k, v)

        # Set values
        for k, v in entries.items():
            if k[0].isupper() and k in Config.DEFAULTS:
                setattr(Config, k, v)

        Config.CONFIG_LOADED = True


config = Config()
