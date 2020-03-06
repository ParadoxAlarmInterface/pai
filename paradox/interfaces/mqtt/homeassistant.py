import asyncio
import json
import logging
import typing
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import sanitize_key

from ...data.model import DetectedPanel
from .core import AbstractMQTTInterface

logger = logging.getLogger("PAI").getChild(__name__)

PreparseResponse = namedtuple("preparse_response", "topics element content")


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    def __init__(self, alarm):
        super().__init__(alarm)
        self.armed = dict()
        self.partitions = {}
        self.zones = {}

        self.availability_topic = self.mqtt.availability_topic
        self.run_status_topic = self.mqtt.run_status_topic

        self.connected_future = (
            asyncio.Future()
        )  # TODO: do not create it, use some other
        panel_detected_future = asyncio.Future()
        first_status_update_future = asyncio.Future()

        def _ready_future_callback(x):
            self._publish_when_ready(
                panel_detected_future.result()["panel"],
                first_status_update_future.result()["status"],
            )

        ready_future = asyncio.ensure_future(
            asyncio.gather(
                self.connected_future, panel_detected_future, first_status_update_future
            )
        )
        ready_future.add_done_callback(_ready_future_callback)

        ps.subscribe(panel_detected_future, "panel_detected")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(first_status_update_future, "status_update")

    def on_connect(self, client, userdata, flags, result):
        # TODO: do not create connected_future, use some other
        if not self.connected_future.done():
            self.connected_future.set_result(True)

    def _handle_labels_loaded(self, data):
        partitions = data.get("partition", {})
        for k, v in partitions.items():
            p_data = {}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data.get("zone", {})

    def _publish_when_ready(self, panel: DetectedPanel, status):
        device = dict(
            manufacturer="Paradox",
            model=panel.model,
            identifiers=["Paradox", panel.model, panel.serial_number],
            name=panel.model,
            sw_version=panel.firmware_version,
        )

        self._publish_run_state_sensor(device, panel.serial_number)

        if "partition" in status:
            self._process_partition_statuses(
                status["partition"], device, panel.serial_number
            )
        if "zone" in status:
            self._process_zone_statuses(status["zone"], device, panel.serial_number)

    def _publish_run_state_sensor(self, device, device_sn):
        configuration_topic = "{}/sensor/{}/{}/config".format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX, device_sn, "run_status"
        )

        config = dict(
            name="Run status",
            unique_id="{}_partition_{}".format(device_sn, "run_status"),
            state_topic=self.run_status_topic,
            # availability_topic=self.availability_topic,
            device=device,
        )

        self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _process_partition_statuses(self, partition_statuses, device, device_sn):
        for p_key, p_status in partition_statuses.items():
            if p_key not in self.partitions:
                continue
            partition = self.partitions[p_key]

            state_topic = "{}/{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_STATES_TOPIC,
                cfg.MQTT_PARTITION_TOPIC,
                sanitize_key(partition["key"]),
                "current_state",
            )

            configuration_topic = "{}/alarm_control_panel/{}/{}/config".format(
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                device_sn,
                sanitize_key(partition["key"]),
            )
            command_topic = "{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_CONTROL_TOPIC,
                cfg.MQTT_PARTITION_TOPIC,
                sanitize_key(partition["key"]),
            )
            config = dict(
                name=partition["label"],
                unique_id="{}_partition_{}".format(device_sn, partition["key"]),
                command_topic=command_topic,
                state_topic=state_topic,
                availability_topic=self.availability_topic,
                device=device,
                payload_disarm="disarm",
                payload_arm_home="arm_stay",
                payload_arm_away="arm",
                payload_arm_night="arm_sleep",
            )

            self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _process_zone_statuses(self, zone_statuses, device, device_sn):
        for z_key, p_status in zone_statuses.items():
            if z_key not in self.zones:
                continue

            zone = self.zones[z_key]

            open_topic = "{}/{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_STATES_TOPIC,
                cfg.MQTT_ZONE_TOPIC,
                sanitize_key(zone["key"]),
                "open",
            )

            config = dict(
                name=zone["label"],
                unique_id="{}_zone_{}_open".format(device_sn, zone["key"]),
                state_topic=open_topic,
                device_class="motion",
                availability_topic=self.availability_topic,
                payload_on="True",
                payload_off="False",
                device=device,
            )

            configuration_topic = "{}/binary_sensor/{}/{}/config".format(
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                device_sn,
                sanitize_key(zone["key"]),
            )

            self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)
