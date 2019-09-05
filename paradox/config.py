import os
import logging


class Config:

    DEFAULTS = { 
        "LOGGING_LEVEL_CONSOLE": logging.INFO,  # See documentation of Logging package
        "LOGGING_LEVEL_FILE": logging.ERROR,
        "LOGGING_FILE": ('/var/log/paradox.log', [type(None), str]),  # or set to file path : '/var/log/paradox.log'
        "LOGGING_FILE_MAX_SIZE": (10, int, (0, 0xFFFFFFFF)),          # Max log file size in MB
        "LOGGING_FILE_MAX_FILES": (2, int, (0, 0xFFFFFFFF)),          # Max old log files to keep
        "LOGGING_DUMP_PACKETS": False,          # Dump RAW Packets to log
        "LOGGING_DUMP_MESSAGES": False,         # Dump Messages to log
        "LOGGING_DUMP_STATUS": False,           # Dump Status to log

        # Development
        "DEVELOPMENT_DUMP_MEMORY": False,

        # Connection Type
        "CONNECTION_TYPE": ('Serial', str, ['IP', 'Serial']),         # Serial or IP

        # Serial Connection Details
        "SERIAL_PORT": '/dev/ttyS1',                                  # Pathname of the Serial Port
        "SERIAL_BAUD": 9600,                                          # Baud rate of the Serial Port. Use 38400(default setting) or 57600 for EVO

        # IP Connection Details
        "IP_CONNECTION_HOST": '127.0.0.1',                            # IP Module address when using direct IP Connection
        "IP_CONNECTION_PORT": (10000, int, (1, 65535)),               # IP Module port when using direct IP Connection
        "IP_CONNECTION_PASSWORD": (b'paradox', [bytes, type(None)]),  # IP Module password. "paradox" is default.
        "IP_CONNECTION_SITEID": (None, [str, type(None)]),            # If defined, connection will be made through this method.
        "IP_CONNECTION_EMAIL": (None, [str, type(None)]),             # Email registered in the site
        "IP_CONNECTION_PANEL_SERIAL": (None, [str, type(None)]),      # Serial number to be used in multi-panel sites. None for first
        "IP_CONNECTION_BARE": False,                                  # IP endpoint connects directly to panel. Used for Serial Tunnels over TCP
        # Paradox
        "KEEP_ALIVE_INTERVAL": 10,        # Interval between status updates

        "LIMITS": {},  # By default all zones will be monitored

        "LABEL_ENCODING": "utf-8",											  # Encoding to use when decoding labels. See https://docs.python.org/3/library/codecs.html#standard-encodings
        "LABEL_REFRESH_INTERVAL": (15 * 60, int, (0, 0xFFFFFFFF)),            # Interval between refresh of labels
        "OUTPUT_PULSE_DURATION": (1, float, (0, 0xFFFFFFFF)),                 # Duration of a PGM pulse in seconds
        "STATUS_REQUESTS": [0, 1, 2, 3, 4, 5],
        "SYNC_TIME": True,                                       # Update panel time
        "PASSWORD": (None, [bytes, type(None)]),                 # PC Password. Set to None if Panel has no Password. In Babyware: Right click on your panel -> Properties -> PC Communication (Babyware) -> PC Communication (Babyware) Tab.

        "POWER_UPDATE_INTERVAL": (60, int, (0, 0xFFFFFFFF)),     # Interval between updates of the Power voltages
        "PUSH_POWER_UPDATE_WITHOUT_CHANGE": True,  # Always notify interfaces of power changes
        "PUSH_UPDATE_WITHOUT_CHANGE": False,       # Always notify interfaces of all changes

        # MQTT
        "MQTT_ENABLE": False,                        # Enable MQTT Interface
        "MQTT_HOST": 'localhost',                    # Hostname or address
        "MQTT_PORT": (1883, int, (1, 65535)),        # TCP Port
        "MQTT_KEEPALIVE": (60, int, (1, 3600)),      # Keep alive
        "MQTT_USERNAME": (None, [str, type(None)]),  # MQTT Username for authentication
        "MQTT_PASSWORD": (None, [str, type(None)]),  # MQTT Password
        "MQTT_RETAIN": True,                         # Publish messages with Retain
        "MQTT_BIND_ADDRESS": '127.0.0.1',
        "MQTT_REPUBLISH_INTERVAL": (60 * 60 * 12, int, (60, 0xFFFFFFFF)),    # Interval for republishing all data
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
        "MQTT_HOMEASSISTANT_CONTROL_TOPIC": 'hass_control',
        "MQTT_OUTPUT_TOPIC": 'outputs',
        "MQTT_KEYPAD_TOPIC": 'keypads',
        "MQTT_STATES_TOPIC": 'states',
        "MQTT_RAW_TOPIC": 'raw',
        "MQTT_HOMEBRIDGE_SUMMARY_TOPIC": 'current',
        "MQTT_PARTITION_HOMEBRIDGE_COMMANDS": {
            'STAY_ARM': 'arm_stay',
            'AWAY_ARM': 'arm',
            'NIGHT_ARM': 'arm_sleep',
            'DISARM': 'disarm'},
        "MQTT_PARTITION_HOMEBRIDGE_STATES": {
            'alarm': 'ALARM_TRIGGERED',
            'arm_stay': 'STAY_ARM',
            'arm': 'AWAY_ARM',
            'arm_sleep': 'NIGHT_ARM',
            'disarm': 'DISARMED'},
        "MQTT_HOMEASSISTANT_SUMMARY_TOPIC": 'current_hass',
        "MQTT_PARTITION_HOMEASSISTANT_STATES": {
            'alarm': 'triggered', 
            'arm_stay': 'armed_home',
            'arm': 'armed_away',
            'arm_sleep': 'armed_night',
            'disarm': 'disarmed'},
        "MQTT_PARTITION_HOMEASSISTANT_COMMANDS": {
            'ARM_HOME': 'arm_stay',
            'ARM_AWAY': 'arm',
            'ARM_NIGHT': 'arm_sleep',
            'DISARM': 'disarm'},
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
        "PUSHBULLET_IGNORE_EVENTS": [
            r"zone,[\w]+,no_delay=True",
            r"zone,[\w]+,exit_delay=.*"],             # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "PUSHBULLET_ALLOW_EVENTS": [r".*"],        # Same as before but as a white list. Default is allow all

        # Pushover
        "PUSHOVER_ENABLE": False,
        "PUSHOVER_KEY": '',                       # Application token for Pushover
        "PUSHOVER_BROADCAST_KEYS": {              # Pushover user or group keys to broadcast notifications to
            #    '<user_key>': '*'                # value can be '*' or comma separated list of device names
        "PUSHOVER_IGNORE_EVENTS": [
            r"zone,[\w]+,no_delay=True",
            r"zone,[\w]+,exit_delay=.*"],             # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "PUSHOVER_ALLOW_EVENTS": [r".*"],          # Same as before but as a white list. Default is allow all

        },

        # Signal
        "SIGNAL_ENABLE": False,
        "SIGNAL_CONTACTS": [],                    # Contacts that are allowed to control the panel and receive notifications through Signal
        "SIGNAL_IGNORE_EVENTS": [
            r"zone,[\w]+,no_delay=True",
            r"zone,[\w]+,exit_delay=.*"],             # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "SIGNAL_ALLOW_EVENTS": [r".*"],            # Same as before but as a white list. Default is allow all

        # GSM
        "GSM_ENABLE": False,
        "GSM_MODEM_BAUDRATE": (115200, int, (9600, 115200)),    # Baudrate of the GSM modem
        "GSM_MODEM_PORT": '',                     # Pathname of the serial port
        "GSM_CONTACTS": [],                       # Contacts that are allowed to control the panel and receive notifications through SMS
        "GSM_IGNORE_EVENTS": [],                  # List of tuples or regexp matching "type:label:property" eg. [(major, minor), "zone:HOME:entry_delay", ...]
        "GSM_ALLOW_EVENTS": [r"partition,[\w]+,alarm=True"],# Same as before but as a white list. Default is to only allow alarm

        # IP Socket Interface
        "IP_INTERFACE_ENABLE": False,
        "IP_INTERFACE_BIND_ADDRESS": '0.0.0.0',
        "IP_INTERFACE_BIND_PORT": (10000, int, (1, 65535)),
        "IP_INTERFACE_PASSWORD": (b'0000', [bytes, type(None)]),

        # Dummy Interface for testing
        "DUMMY_INTERFACE_ENABLE": False,

        #Homie Interface
        "HOMIE_INTERFACE_ENABLE": True,
        "HOMIE_BASE_TOPIC": "homie/",
        "HOMIE_NODE_FILTER": {
            'zone': ['open']
        }
    }

    CONFIG_LOADED = False
    CONFIG_FILE_LOCATION = None,

    def __init__(self):
        if Config.CONFIG_LOADED:
            return

    @staticmethod
    def load(alt_location=None):
        Config.CONFIG_LOADED = False

        env_config_path = os.environ.get('PAI_CONFIG_FILE')

        if alt_location is not None:
            locations = [alt_location]
        elif env_config_path:
            locations = [env_config_path]
        else:
            locations = ['/etc/pai/pai.conf',
                         '/usr/local/etc/pai/pai.conf',
                         '~/.local/etc/pai.conf',
                         'pai.conf'
                         ]

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
            if isinstance(v, tuple):
                v = v[0]

            setattr(Config, k, v)

        # Set values
        for k, v in entries.items():
            if k[0].isupper() and k in Config.DEFAULTS:
                default = Config.DEFAULTS.get(k)
                
                if isinstance(default, tuple) and 2 <= len(default) <= 3:
                    default_type = default[1]

                    if not isinstance(default_type, list):
                        default_type = [default_type]

                else:
                    default_type = [type(default)]

                if float in default_type and not int in default_type:
                    default_type.append(int)
                if int in default_type and not float in default_type:
                    default_type.append(float)

                if type(v) in default_type:
                    setattr(Config, k, v)
                else:
                    logging.error("Invalid value type {} for config argument {}. Allowed are: {}".format(type(v), k, default_type))
                    raise (Exception("Error parsing configuration type"))

                if isinstance(default, tuple) and len(default) == 3:
                    expected_value = default[2]
                    valid = False

                    if isinstance(v, int):
                        if expected_value[0] <= v <= expected_value[1]:
                            valid = True
                    elif isinstance(v, str):
                        if v in expected_value:
                            valid = True
                    else:
                        valid = True

                    if valid:
                        setattr(Config, k, v)
                    else:
                        logging.error("Invalid value for config argument {} {}. Allowed are: {}".format(type(v), k, expected_value))
                        raise(Exception("Error parsing configuration value"))

        for args in os.environ:
            if not args.startswith('PAI_') and len(args) > 4:
                continue
            opt = args[4:]
            if opt in Config.DEFAULTS:
                v = os.environ[args]
                if v.isdigit():
                    v = int(v)

                setattr(Config, opt, v)

        Config.CONFIG_LOADED = True


config = Config()
