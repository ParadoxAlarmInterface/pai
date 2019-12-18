import json
import logging
import typing
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import sanitize_key
from .core import AbstractMQTTInterface

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
        self.detected_panel = {}

        self.first_status = True

        # TODO: Maybe homeassistant needs a separate status topic
        self.availability_topic = '{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, 'MQTTInterface')

    async def run(self):
        ps.subscribe(self._handle_status_update, "status_update")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(self._handle_panel_detected, "panel_detected")

        await super().run()

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
        partitions = data.get('partition', {})
        for k, v in partitions.items():
            p_data = {}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data.get('zone', {})

    def _handle_status_update(self, status):
        if self.mqtt.connected:
            if 'partition' in status:
                self._process_partition_statuses(status['partition'])
            if 'zone' in status:
                self._process_zone_statuses(status['zone'])

            self.first_status = False

    def _process_partition_statuses(self, partition_statuses):
        for p_key, p_status in partition_statuses.items():
            if p_key not in self.partitions:
                continue
            partition = self.partitions[p_key]

            state_topic = '{}/{}/{}/{}/{}'.format(
                cfg.MQTT_BASE_TOPIC,
                 cfg.MQTT_STATES_TOPIC,
                 cfg.MQTT_PARTITION_TOPIC,
                 sanitize_key(partition['key']),
                 'current_state'
            )

            if self.first_status:  # For HASS auto discovery
                configuration_topic = '{}/alarm_control_panel/{}/{}/config'.format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    self.detected_panel.get('serial_number', 'pai'),
                    sanitize_key(partition['key'])
                )
                command_topic = '{}/{}/{}/{}'.format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_CONTROL_TOPIC,
                    cfg.MQTT_PARTITION_TOPIC,
                    sanitize_key(partition['key'])
                )
                config = dict(
                    name=partition['label'],
                    unique_id="{}_partition_{}".format(self.detected_panel.get('serial_number', 'pai'), partition['key']),
                    command_topic=command_topic,
                    state_topic=state_topic,
                    availability_topic=self.availability_topic,
                    device=self.device,
                    payload_disarm="disarm",
                    payload_arm_home="arm_stay",
                    payload_arm_away="arm",
                    payload_arm_night="arm_sleep"
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

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
                    sanitize_key(zone['key']),
                    'open'
                )

                config = dict(
                    name=zone['label'],
                    unique_id="{}_zone_{}_open".format(self.detected_panel.get('serial_number', 'pai'), zone['key']),
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
                    sanitize_key(zone['key'])
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)