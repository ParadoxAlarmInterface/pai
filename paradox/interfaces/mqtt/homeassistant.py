import logging
import typing
from collections import namedtuple

from .core import AbstractMQTTInterface, sanitize_topic_part, ELEMENT_TOPIC_MAP

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)

PreparseResponse = namedtuple('preparse_response', 'topics element content')


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    name = "homeassistant_mqtt"

    def __init__(self):
        super().__init__()
        self.armed = dict()
        self.partitions = {}

    def run(self):
        required_mappings = 'alarm,arm,arm_stay,arm_sleep,disarm'.split(',')
        # if cfg.MQTT_HOMEBRIDGE_ENABLE:
        #     self._check_config_mappings('MQTT_PARTITION_HOMEBRIDGE_STATES', required_mappings)
        self._check_config_mappings('MQTT_PARTITION_HOMEASSISTANT_STATES', required_mappings)

        self.subscribe_callback(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_HOMEASSISTANT_CONTROL_TOPIC, cfg.MQTT_PARTITION_TOPIC),
            self._mqtt_handle_partition_control
        )

        super().run()

    def _preparse_message(self, message) -> typing.Optional[PreparseResponse]:
        logger.info("message topic={}, payload={}".format(
            message.topic, str(message.payload.decode("utf-8"))))

        if message.retain:
            logger.warning("Ignoring retained commands")
            return None

        if self.alarm is None:
            logger.warning("No alarm. Ignoring command")
            return None

        topic = message.topic.split(cfg.MQTT_BASE_TOPIC)[1]

        topics = topic.split("/")

        if len(topics) < 3:
            logger.error(
                "Invalid topic in mqtt message: {}".format(message.topic))
            return None

        content = message.payload.decode("latin").strip()

        element = None
        if len(topics) >= 4:
            element = topics[3]

        return PreparseResponse(topics, element, content)

    def _mqtt_handle_partition_control(self, client, userdata, message):
        prep = self._preparse_message(message)
        if prep:
            topics, element, command = prep
            # if command in cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS and cfg.MQTT_HOMEBRIDGE_ENABLE:
            #     command = cfg.MQTT_PARTITION_HOMEBRIDGE_COMMANDS[command]
            if command not in cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS:
                logger.warning("Invalid command: {}={}".format(element, command))

            command = cfg.MQTT_PARTITION_HOMEASSISTANT_COMMANDS[command]

            logger.debug("Partition command: {} = {}".format(element, command))
            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))

    def _handle_panel_change(self, change):
        attribute = change['property']
        label = change['label']
        value = change['value']
        initial = change['initial']
        element = change['type']

        if element in ELEMENT_TOPIC_MAP:
            element_topic = ELEMENT_TOPIC_MAP[element]
        else:
            element_topic = element

        if element == 'partition':
            # if cfg.MQTT_HOMEBRIDGE_ENABLE:
            #     self._handle_change_external(element, label, attribute, value, element_topic,
            #                                  cfg.MQTT_PARTITION_HOMEBRIDGE_STATES, cfg.MQTT_HOMEBRIDGE_SUMMARY_TOPIC,
            #                                  'hb')

            self._handle_change_external(element, label, attribute, value, element_topic,
                                         cfg.MQTT_PARTITION_HOMEASSISTANT_STATES,
                                         cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC,
                                         'hass')

    def _handle_change_external(self, element, label, attribute,
                                value, element_topic, states_map,
                                summary_topic, service):

        if service not in self.armed:
            self.armed[service] = dict()

        if label not in self.armed[service]:
            self.armed[service][label] = dict(attribute=None, state=None, alarm=False)

        # Property changing to True: Alarm or arm
        if value:
            if attribute in ['alarm', 'bell_activated', 'strobe_alarm', 'silent_alarm', 'audible_alarm'] and not \
                    self.armed[service][label]['alarm']:
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
            if attribute in ['alarm', 'strobe_alarm', 'audible_alarm', 'bell_activated', 'silent_alarm'] and \
                    self.armed[service][label]['alarm']:
                state = self.armed[service][label]['state']  # Restore the ARM state
                self.armed[service][label]['alarm'] = False  # Reset alarm state

            elif attribute in ['arm_stay', 'arm', 'arm_sleep'] and self.armed[service][label]['attribute'] == attribute:
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

    def _check_config_mappings(self, config_parameter, required_mappings):
        # Check states_map
        keys = getattr(cfg, config_parameter).keys()
        missing_mappings = [k for k in required_mappings if k not in keys]
        if len(missing_mappings):
            logger.warning(', '.join(missing_mappings) + " keys are missing from %s config." % config_parameter)
