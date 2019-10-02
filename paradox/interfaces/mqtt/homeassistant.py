import logging
import typing
import json
from collections import namedtuple

from .core import AbstractMQTTInterface, sanitize_topic_part, ELEMENT_TOPIC_MAP

from paradox.config import config as cfg
from paradox.lib import ps

logger = logging.getLogger('PAI').getChild(__name__)

PreparseResponse = namedtuple('preparse_response', 'topics element content')


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    name = "homeassistant_mqtt"

    def __init__(self):
        super().__init__()
        self.armed = dict()
        self.partitions = {}
        self.zones = {}
        self.device = {}

        self.first_status = True

        # TODO: Maybe homeassistant needs a separate status topic
        self.availability_topic = '{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, 'MQTTInterface')

    async def run(self):
        required_mappings = 'alarm,arm,arm_stay,arm_sleep,disarm'.split(',')
        # if cfg.MQTT_HOMEBRIDGE_ENABLE:
        #     self._check_config_mappings('MQTT_PARTITION_HOMEBRIDGE_STATES', required_mappings)
        self._check_config_mappings('MQTT_PARTITION_HOMEASSISTANT_STATES', required_mappings)

        ps.subscribe(self._handle_status_update, "status_update")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(self._handle_panel_detected, "panel_detected")

        await super().run()

    def on_connect(self, client, userdata, flags, result):
        super().on_connect(client, userdata, flags, result)
        self.subscribe_callback(
            "{}/{}/{}/#".format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_HOMEASSISTANT_CONTROL_TOPIC, cfg.MQTT_PARTITION_TOPIC),
            self._mqtt_handle_partition_control
        )

    def _handle_panel_detected(self, panel):
        self.detected_panel = panel
        self.device = dict(
            manufacturer="Paradox",
            model=panel.get('model'),
            identifiers=["Paradox", panel.get('model'), panel.get('serial_number')],
            name=panel.get('model'),
            sw_version=panel.get('firmware_version')
        )

    def _handle_labels_loaded(self, data):
        partitions = data['partition']
        for k, v in partitions.items():
            p_data = {'status': None}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data['zone']

    def _handle_status_update(self, status):
        self._process_partition_statuses(status['partition'])
        self._process_zone_statuses(status['zone'])

        self.first_status = False

    def _process_partition_statuses(self, partition_statuses):
        for p_key, p_status in partition_statuses.items():
            if p_key not in self.partitions:
                continue
            partition = self.partitions[p_key]

            if any([
                p_status.get('fire_alarm'),
                p_status.get('audible_alarm'),
                p_status.get('silent_alarm'),
                p_status.get('panic_alarm')
            ]):
                new_status = 'triggered'
            elif p_status.get('arm'):
                if p_status.get('exit_delay'):
                    new_status = 'pending'
                elif p_status.get('arm_stay'):
                    new_status = 'armed_home'
                elif p_status.get('arm_away'):
                    new_status = 'armed_away'
                else:
                    new_status = 'armed_away'
            else:
                new_status = 'disarmed'

            state_topic = '{}/{}/{}/{}/{}'.format(
                cfg.MQTT_BASE_TOPIC,
                 cfg.MQTT_STATES_TOPIC,
                 cfg.MQTT_PARTITION_TOPIC,
                 sanitize_topic_part(partition['key']),
                 cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC
            )

            if self.first_status:  # For HASS auto discovery
                configuration_topic = '{}/alarm_control_panel/{}/{}/config'.format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    self.detected_panel.get('serial_number', 'pai'),
                    sanitize_topic_part(partition['key'])
                )
                command_topic = '{}/{}/{}/{}/{}'.format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_HOMEASSISTANT_CONTROL_TOPIC,
                    cfg.MQTT_PARTITION_TOPIC,
                    sanitize_topic_part(partition['key']),
                    cfg.MQTT_HOMEASSISTANT_CONTROL_TOPIC
                )
                config = dict(
                    name=partition['label'],
                    unique_id="{}_partition_{}".format(self.detected_panel.get('serial_number', 'pai'), partition['key']),
                    command_topic=command_topic,
                    state_topic=state_topic,
                    availability_topic=self.availability_topic,
                    device=self.device
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

            if new_status and partition['status'] != new_status:
                self.alarm.update_properties('partition', partition['key'], {cfg.MQTT_HOMEASSISTANT_SUMMARY_TOPIC: new_status})
            partition['status'] = new_status

    def _process_zone_statuses(self, zone_statuses):
        for z_key, p_status in zone_statuses.items():
            if z_key not in self.zones:
                continue

            zone = self.zones[z_key]

            if self.first_status:  # For HASS auto discovery
                open_topic = '{}/{}/{}/{}/{}'.format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_STATES_TOPIC,
                    cfg.MQTT_ZONE_TOPIC,
                    sanitize_topic_part(zone['key']),
                    'open'
                )

                config = dict(
                    name=zone['label'],
                    unique_id="{}_zone_{}".format(self.detected_panel.get('serial_number', 'pai'), zone['key']),
                    state_topic=open_topic,
                    device_class="motion",
                    availability_topic=self.availability_topic,
                    payload_on="True",
                    payload_off="False",
                    device=self.device
                )

                configuration_topic = '{}/binary_sensor/{}/{}/config'.format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    self.detected_panel.get('serial_number', 'pai'),
                    sanitize_topic_part(zone['key'])
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

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

    def _check_config_mappings(self, config_parameter, required_mappings):
        # Check states_map
        keys = getattr(cfg, config_parameter).keys()
        missing_mappings = [k for k in required_mappings if k not in keys]
        if len(missing_mappings):
            logger.warning(', '.join(missing_mappings) + " keys are missing from %s config." % config_parameter)
