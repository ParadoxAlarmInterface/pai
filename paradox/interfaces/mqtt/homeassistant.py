import json
import logging
import typing
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import sanitize_key
from .core import AbstractMQTTInterface
from ...data.model import DetectedPanel

logger = logging.getLogger('PAI').getChild(__name__)

PreparseResponse = namedtuple('preparse_response', 'topics element content')


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    def __init__(self, alarm):
        super().__init__(alarm)
        self.armed = dict()
        self.partitions = {}
        self.zones = {}
        self.device = {}

        self.first_status = True

        self.availability_topic = self.mqtt.availability_topic
        self.run_status_topic = self.mqtt.run_status_topic

    def on_connect(self, mqttc, userdata, flags, result):
        ps.subscribe(self._handle_status_update, "status_update")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(self._handle_panel_detected, "panel_detected")

    def _publish_run_state_sensor(self):
        configuration_topic = '{}/sensor/{}/{}/config'.format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
            self.device_serial_number,
            'run_status'
        )

        config = dict(
            name='Run status',
            unique_id="{}_partition_{}".format(
                self.device_serial_number,
                'run_status'
            ),
            state_topic=self.run_status_topic,
            # availability_topic=self.availability_topic,
            device=self.device
        )

        self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _handle_panel_detected(self, panel: DetectedPanel):
        self.device_serial_number = panel.serial_number

        self.device = dict(
            manufacturer="Paradox",
            model=panel.model,
            identifiers=["Paradox", panel.model, panel.serial_number],
            name=panel.model,
            sw_version=panel.firmware_version
        )

        self._publish_run_state_sensor()

    def _handle_labels_loaded(self, data):
        partitions = data.get('partition', {})
        for k, v in partitions.items():
            p_data = {}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data.get('zone', {})

    def _handle_status_update(self, status):
        if self.mqtt.connected and self.device:
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
                    self.device_serial_number,
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
                    unique_id="{}_partition_{}".format(
                        self.device_serial_number,
                        partition['key']
                    ),
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
                    unique_id="{}_zone_{}_open".format(self.device_serial_number, zone['key']),
                    state_topic=open_topic,
                    device_class="motion",
                    availability_topic=self.availability_topic,
                    payload_on="True",
                    payload_off="False",
                    device=self.device
                )

                configuration_topic = '{}/binary_sensor/{}/{}/config'.format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    self.device_serial_number,
                    sanitize_key(zone['key'])
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)
