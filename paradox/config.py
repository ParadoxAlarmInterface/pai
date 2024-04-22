import logging
import os
import re
import sys


class Config:
    DEFAULTS = {
        "LOGGING_LEVEL_CONSOLE": logging.INFO,  # See documentation of Logging package
        "LOGGING_LEVEL_FILE": logging.ERROR,
        "LOGGING_FILE": (
            None,
            [type(None), str],
        ),  # or set to file path : '/var/log/paradox.log'
        "LOGGING_FILE_MAX_SIZE": (10, int, (0, 0xFFFFFFFF)),  # Max log file size in MB
        "LOGGING_FILE_MAX_FILES": (
            2,
            int,
            (0, 0xFFFFFFFF),
        ),  # Max old log files to keep
        "LOGGING_DUMP_PACKETS": False,  # Dump RAW Packets to log
        "LOGGING_DUMP_MESSAGES": False,  # Dump Messages to log
        "LOGGING_DUMP_STATUS": False,  # Dump Status to log
        "LOGGING_DUMP_EVENTS": False,  # Dump Event details to log
        # Development
        "DEVELOPMENT_DUMP_MEMORY": False,
        # Connection Type
        "CONNECTION_TYPE": ("Serial", str, ["IP", "Serial"]),  # Serial or IP
        # Serial Connection Details
        "SERIAL_PORT": "/dev/ttyS1",  # Pathname of the Serial Port
        "SERIAL_BAUD": 9600,  # Baud rate of the Serial Port. Use 38400(default setting) or 57600 for EVO
        # IP Connection Details
        "IP_CONNECTION_HOST": "127.0.0.1",  # IP Module address when using direct IP Connection
        "IP_CONNECTION_PORT": (
            10000,
            int,
            (1, 65535),
        ),  # IP Module port when using direct IP Connection
        "IP_CONNECTION_PASSWORD": (
            "paradox",
            [str, bytes, type(None)],
        ),  # IP Module password. "paradox" is default.
        "IP_CONNECTION_SITEID": (
            None,
            [str, type(None)],
        ),  # If defined, connection will be made through this method.
        "IP_CONNECTION_EMAIL": (
            None,
            [str, type(None)],
        ),  # Email registered in the site
        "IP_CONNECTION_PANEL_SERIAL": (
            None,
            [str, type(None)],
        ),  # Serial number to be used in multi-panel sites. None for first
        "IP_CONNECTION_BARE": False,  # IP endpoint connects directly to panel. Used for Serial Tunnels over TCP
        # Paradox
        "KEEP_ALIVE_INTERVAL": 10,  # Interval between status updates
        "IO_TIMEOUT": 0.5,  # Timeout for IO operations
        "LIMITS": {},  # By default all zones will be monitored
        "LABEL_ENCODING": "paradox-en",  # Encoding to use when decoding labels. paradox-* or https://docs.python.org/3/library/codecs.html#standard-encodings
        "LABEL_REFRESH_INTERVAL": (
            15 * 60,
            int,
            (0, 0xFFFFFFFF),
        ),  # Interval between refresh of labels
        "OUTPUT_PULSE_DURATION": (
            1,
            float,
            (0, 0xFFFFFFFF),
        ),  # Duration of a PGM pulse in seconds
        "SYNC_TIME": False,  # Update panel time periodically when time drifts more than SYNC_TIME_MIN_DRIFT
        "SYNC_TIME_MIN_DRIFT": (
            120,
            int,
            (120, 0xFFFFFFFF),
        ),  # Minimum time drift in seconds to initiate time sync
        "SYNC_TIME_TIMEZONE": "",  # By default pai uses the same timezone as pai host
        "PASSWORD": (
            None,
            [int, str, bytes, type(None)],
        ),  # PC Password. Set to None if Panel has no Password. In Babyware: Right click on your panel -> Properties -> PC Communication (Babyware) -> PC Communication (Babyware) Tab.
        "PUSH_UPDATE_WITHOUT_CHANGE": False,  # Always notify interfaces of all changes
        # MQTT
        "MQTT_ENABLE": False,  # Enable MQTT Interface
        "MQTT_HOST": "127.0.0.1",  # Hostname or address
        "MQTT_PORT": (
            1883,
            int,
            (1, 65535),
        ),  # TCP Port (TLS port if MQTT_TLS_CERT_PATH is set)
        "MQTT_TLS_CERT_PATH": (
            None,
            [str, type(None)],
        ),  # Path to ca cert (/etc/pai/certs/ca.pem), if you want TLS
        "MQTT_KEEPALIVE": (60, int, (1, 3600)),  # Keep alive
        "MQTT_USERNAME": (None, [str, type(None)]),  # MQTT Username for authentication
        "MQTT_PASSWORD": (None, [str, type(None)]),  # MQTT Password
        "MQTT_RETAIN": True,  # Publish messages with Retain
        "MQTT_QOS": (
            0,
            int,
            (0, 2),
        ),  # Publish messages with QOS level (0 - fire and forget, 1 - at least once, 2 - exactly once)
        "MQTT_PROTOCOL": ("3.1.1", str, ("3.1", "3.1.1", "5")),  # Protocol to use
        "MQTT_TRANSPORT": ("tcp", str, ("tcp", "websockets")),  # Transport to use
        "MQTT_BIND_ADDRESS": "",  # MQTT Bind address (Paho default)
        "MQTT_BIND_PORT": 0,  # MQTT Bind port (Paho default)
        "MQTT_REPUBLISH_INTERVAL": (
            60 * 60 * 12,
            int,
            (60, 0xFFFFFFFF),
        ),  # Interval for republishing all data
        "MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE": False,
        "MQTT_HOMEASSISTANT_CODE": (None, [str, type(None)]),
        "MQTT_HOMEASSISTANT_ENTITY_PREFIX": "",  # If you want to prefix all entities you can use: "Paradox {serial_number} ", placeholders "serial_number" and "model" are supported. Default: "" - no prefix
        # MQTT Topics
        "MQTT_BASE_TOPIC": "paradox",  # Root of all topics
        "MQTT_ZONE_TOPIC": "zones",  # Base for zone states
        "MQTT_PARTITION_TOPIC": "partitions",  # Base for partition states
        "MQTT_BUS_TOPIC": "buses",  # Base for buses states
        "MQTT_MODULE_TOPIC": "bus-module",  # Base for bus module states
        "MQTT_SYSTEM_TOPIC": "system",  # Base for panel states
        "MQTT_REPEATER_TOPIC": "repeaters",  # Base for repeater states
        "MQTT_USER_TOPIC": "users",  # Base for user states
        "MQTT_EVENTS_TOPIC": "events",  # Base for events
        "MQTT_CONTROL_TOPIC": "control",  # Base for control of other elements (ROOT/CONTROL/TYPE)
        "MQTT_DEFINITION_TOPIC": "definitions",  # Base for definitions
        "MQTT_HOMEASSISTANT_CONTROL_TOPIC": "hass_control",
        "MQTT_HOMEASSISTANT_DISCOVERY_PREFIX": "homeassistant",
        "MQTT_OUTPUT_TOPIC": "outputs",
        "MQTT_DOOR_TOPIC": "doors",
        "MQTT_KEYPAD_TOPIC": "keypads",
        "MQTT_STATES_TOPIC": "states",
        "MQTT_RAW_TOPIC": "raw",
        "MQTT_NOTIFICATIONS_TOPIC": "notifications",
        "MQTT_SEND_PANIC_TOPIC": "panic",
        "MQTT_PUBLISH_RAW_EVENTS": True,
        "MQTT_PUBLISH_DEFINITIONS": False,  # Publish definitions of partitions/zones/users to mqtt.
        "MQTT_PREFIX_DEVICE_NAME": False,  # Add device ID as prefix to entity names: Paradox 12345678
        "MQTT_INTERFACE_TOPIC": "interface",
        "MQTT_TOGGLE_CODES": {},
        "MQTT_USE_NUMERIC_STATES": False,  # use 0 and 1 instead of True and False
        "MQTT_DASH_PUBLISH": False,
        "MQTT_DASH_TOPIC": "metrics/exchange/pai",
        "MQTT_DASH_TEMPLATE": "/etc/pai/mqtt_dash.txt",
        "MQTT_CHALLENGE_SECRET": (
            None,
            [str, type(None)],
        ),  # MQTT Command authorization challenge
        "MQTT_CHALLENGE_TOPIC": "challenge",
        "MQTT_CHALLENGE_ROUNDS": 1000,
        # Interfaces text command alias
        "COMMAND_ALIAS": {  # alias for commands through text based interfaces
            "arm": "partition all arm",
            "disarm": "partition all disarm",
        },
        "MQTT_PUBLISH_COMMAND_STATUS": False,
        "MQTT_COMMAND_STATUS_TOPIC": "command_status",
        # MQTT command aliases
        "MQTT_COMMAND_ALIAS": {
            # For homebridge
            "armed_home": "arm_stay",
            "armed_night": "arm_sleep",
            "armed_away": "arm",
            "disarmed": "disarm",
        },
        # Home Assistant Notifications (HASS.io required)
        "HOMEASSISTANT_NOTIFICATIONS_ENABLE": False,
        "HOMEASSISTANT_NOTIFICATIONS_NOTIFIER_NAME": "notify",
        "HOMEASSISTANT_NOTIFICATIONS_MIN_EVENT_LEVEL": (
            "INFO",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
        "HOMEASSISTANT_PUBLISH_PARTITION_PROPERTIES": [  # List of partition properties to publish
            "target_state",
            "current_state",
        ],
        "HOMEASSISTANT_PUBLISH_ZONE_PROPERTIES": [  # List of zone properties to publish
            "open",
            "tamper",
        ],
        "HOMEASSISTANT_NOTIFICATIONS_IGNORE_EVENTS": [],  # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "HOMEASSISTANT_NOTIFICATIONS_ALLOW_EVENTS": [],  # Same as before but as a white list. Default is use EVENT_FILTERS
        "HOMEASSISTANT_NOTIFICATIONS_EVENT_FILTERS": [  # list of tags, property changes to include or exclude. See event.py for tag list
            "live,alarm,-restore",
            "trouble,-clock",
            "live,tamper",
        ],
        # Pushbullet
        "PUSHBULLET_ENABLE": False,
        "PUSHBULLET_KEY": "",  # Authentication key used for Pushbullet
        "PUSHBULLET_DEVICE": "pai",  # Destination device for notifications
        "PUSHBULLET_CONTACTS": [],  # Pushbullet user identifiers for notifications and interaction
        "PUSHBULLET_IGNORE_EVENTS": [],  # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "PUSHBULLET_ALLOW_EVENTS": [],  # Same as before but as a white list. Default is use EVENT_FILTERS
        "PUSHBULLET_EVENT_FILTERS": [  # list of tags, property changes to include or exclude. See event.py for tag list
            "live,alarm,-restore",
            "trouble,-clock",
            "live,tamper",
        ],
        "PUSHBULLET_MIN_EVENT_LEVEL": (
            "INFO",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
        # Pushover
        "PUSHOVER_ENABLE": False,
        "PUSHOVER_KEY": "",  # Application token for Pushover
        "PUSHOVER_BROADCAST_KEYS": [  # Pushover user or group keys to broadcast notifications to
            #    {'user_key':'<user_key>', 'devices': '*'}                # value can be '*' or comma separated list of device names
        ],
        "PUSHOVER_IGNORE_EVENTS": [],  # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "PUSHOVER_ALLOW_EVENTS": [],  # Same as before but as a white list. Default is use EVENT_FILTERS
        "PUSHOVER_EVENT_FILTERS": [  # list of tags, property changes to include or exclude. See event.py for tag list
            "live,alarm,-restore",
            "trouble,-clock",
            "live,tamper",
        ],
        "PUSHOVER_MIN_EVENT_LEVEL": (
            "INFO",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
        # Signal
        "SIGNAL_ENABLE": False,
        "SIGNAL_CONTACTS": [],  # Contacts that are allowed to control the panel and receive notifications through Signal
        "SIGNAL_IGNORE_EVENTS": [],  # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "SIGNAL_ALLOW_EVENTS": [],  # Same as before but as a white list. Default is use EVENT_FILTERS
        "SIGNAL_EVENT_FILTERS": [  # list of tags, property changes to include or exclude. See event.py for tag list
            "live,alarm,-restore",
            "trouble,-clock",
            "live,tamper",
        ],
        "SIGNAL_MIN_EVENT_LEVEL": (
            "INFO",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
        # GSM
        "GSM_ENABLE": False,
        "GSM_MODEM_BAUDRATE": (
            115200,
            int,
            (9600, 115200),
        ),  # Baudrate of the GSM modem
        "GSM_MODEM_PORT": "",  # Pathname of the serial port
        "GSM_CONTACTS": [],  # Contacts that are allowed to control the panel and receive notifications through SMS
        "GSM_IGNORE_EVENTS": [],  # List of tuples or regexp matching "type,label,property=value,property2=value" eg. [(major, minor), "zone:HOME:entry_delay=True", ...]
        "GSM_ALLOW_EVENTS": [],  # Same as before but as a white list. Default is use EVENT_FILTERS
        "GSM_EVENT_FILTERS": [  # list of tags, property changes to include or exclude. See event.py for tag list
            "live,zone,alarm,trigger"
        ],
        "GSM_MIN_EVENT_LEVEL": (
            "CRITICAL",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
        # IP Socket Interface
        "IP_INTERFACE_ENABLE": False,
        "IP_INTERFACE_BIND_ADDRESS": "0.0.0.0",
        "IP_INTERFACE_BIND_PORT": (10000, int, (1, 65535)),
        "IP_INTERFACE_PASSWORD": ("paradox", [str, bytes, type(None)]),
        # Dummy Interface for testing
        "DUMMY_INTERFACE_ENABLE": False,
        "DUMMY_EVENT_FILTERS": [
            "live,alarm-restore",
            "live,trouble-clock",
            "live,tamper",
            "live,arm",
            "live,disarm",
        ],
        "DUMMY_MIN_EVENT_LEVEL": (
            "DEBUG",
            str,
            ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        ),
    }

    CONFIG_LOADED = False
    CONFIG_FILE_LOCATION = (None,)

    def __dir__(self):
        return list(self.DEFAULTS.keys()) + list(self.__class__.__dict__) + dir(super())

    def __init__(self):
        self._reset_defaults()

    def load(self, alt_location=None):
        self.CONFIG_LOADED = False

        self._find_config(alt_location)

        sys.stdout.write(
            "Attempting to load configuration from %s\n" % self.CONFIG_FILE_LOCATION
        )
        entries = self._read_config()
        self._update_from_environment(entries)

        # Set values
        for k, v in entries.items():
            if k[0].isupper() and k in self.DEFAULTS:
                default = self.DEFAULTS.get(k)

                if isinstance(default, tuple) and 2 <= len(default) <= 3:
                    default_type = default[1]

                    if not isinstance(default_type, list):
                        default_type = [default_type]

                else:
                    default_type = [type(default)]

                if float in default_type and int not in default_type:
                    default_type.append(int)
                if int in default_type and float not in default_type:
                    default_type.append(float)
                if type(v) in default_type:
                    setattr(self, k, v)
                else:
                    err = "Error parsing configuration: Invalid value type {} for config argument {}. Allowed are: {}".format(
                        type(v), k, default_type
                    )
                    sys.stderr.write(err + "\n")
                    raise (Exception(err))

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
                        setattr(self, k, v)
                    else:
                        err = "Error parsing configuration value: Invalid value for config argument {} (type {}). Allowed are in: {}".format(
                            k, type(v), expected_value
                        )
                        sys.stderr.write(err + "\n")
                        raise (Exception(err))

        self.CONFIG_LOADED = True

    def _update_from_environment(self, entries):
        # Updates values from env variables
        for args in os.environ:
            if not args.startswith("PAI_") or len(args) < 5:
                continue
            opt = args[4:]
            if opt in self.DEFAULTS:
                v = os.environ[args]
                if v.isdigit():
                    v = int(v)

                entries[opt] = v

    def _read_config(self):
        entries = {}
        conf_extension = os.path.splitext(self.CONFIG_FILE_LOCATION)[1]
        if conf_extension in [".conf", ".py"]:
            with open(self.CONFIG_FILE_LOCATION) as f:
                exec(f.read(), None, entries)
        elif conf_extension in [".json"]:
            import json

            with open(self.CONFIG_FILE_LOCATION) as f:
                entries = json.load(f)
        elif conf_extension in [".yaml"]:
            import yaml

            with open(self.CONFIG_FILE_LOCATION) as f:
                entries = yaml.safe_load(f)
        else:
            err = "ERROR: Unsupported configuration file type"
            sys.stderr.write(err + "\n")
            raise (Exception(err))
        return entries

    def _find_config(self, alt_location):
        env_config_path = os.environ.get("PAI_CONFIG_FILE")
        if alt_location is not None:
            locations = [alt_location]
        elif env_config_path:
            locations = [env_config_path]
        else:
            filenames = ["pai.conf", "pai.json", "pai.yaml"]
            locations = [
                os.path.join(dir, filename)
                for dir in [
                    os.path.realpath(os.getcwd()),
                    os.path.expanduser("~/.local/etc"),
                    "/etc/pai",
                    "/usr/local/etc/pai",
                ]
                for filename in filenames
            ]
        for location in locations:
            location = os.path.expanduser(location)
            if os.path.exists(location) and os.path.isfile(location):
                self.CONFIG_FILE_LOCATION = location
                break
        else:
            err = f"ERROR: Could not find configuration file. Tried: {locations}"
            sys.stderr.write(err + "\n")
            raise (Exception(err))

    def _reset_defaults(self):
        # Reset defaults
        for k, v in self.DEFAULTS.items():
            if isinstance(v, tuple):
                v = v[0]

            setattr(self, k, v)


config = Config()

comma_splitter_re = re.compile(r"\s*,\s*")
range_re = re.compile(r"(\d+)\s*-(\d+)\s*$")


def string_to_id_list(input: str):
    arr = []
    blocks = comma_splitter_re.split(input)
    for block in blocks:
        range_match = range_re.match(block)
        if range_match:
            arr += range(int(range_match.group(1)), int(range_match.group(2)) + 1)
        else:
            try:
                arr.append(int(block))
            except ValueError:
                pass

    return arr


def get_limits_for_type(elem_type: str, default: list = None):
    limits = config.LIMITS.get(elem_type, default)
    if limits is None:
        return default

    if isinstance(limits, list):
        return limits

    if isinstance(limits, range):
        return list(limits)

    if isinstance(limits, str):
        if "auto" in limits:
            return default
        return string_to_id_list(limits)
