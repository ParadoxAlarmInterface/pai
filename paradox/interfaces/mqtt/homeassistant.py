import asyncio
import json
import logging
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import SerializableToJSONEncoder
from .entities.abstract_entity import AbstractEntity
from .entities.device import Device
from .entities.factory import MQTTAutodiscoveryEntityFactory

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
        self.pgms = {}

        self.entity_factory = MQTTAutodiscoveryEntityFactory(self.mqtt.availability_topic)

        self.run_status_topic = self.mqtt.pai_status_topic

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
        self.pgms = data.get("pgm", {})

    def _publish_when_ready(self, panel: DetectedPanel, status):
        self.entity_factory.set_device(Device(panel))

        self._publish_pai_state_sensor_config()
        if "partition" in status:
            self._publish_partition_configs(status["partition"])
        if "zone" in status:
            self._publish_zone_configs(status["zone"])
        if "pgm" in status:
            self._publish_pgm_configs(status["pgm"])
        if "system" in status:
            self._publish_system_property_configs(status['system'])

    def _publish_config(self, entity: AbstractEntity):
        self.publish(entity.configuration_topic, json.dumps(entity, cls=SerializableToJSONEncoder), 0,
                     cfg.MQTT_RETAIN)

    def _publish_pai_state_sensor_config(self):
        pai_state_sensor_config = self.entity_factory.make_pai_status_sensor(self.run_status_topic)
        self._publish_config(pai_state_sensor_config)

    def _publish_partition_configs(self, partition_statuses):
        for partition_key, partition_status in partition_statuses.items():
            if partition_key not in self.partitions:
                continue

            partition = self.partitions[partition_key]
            code = cfg.MQTT_HOMEASSISTANT_CODE or None  # returns None on empty string. For HA Addon Schema parsing

            partition_alarm_control_panel_config = self.entity_factory.make_alarm_control_panel_config(partition, code)
            self._publish_config(partition_alarm_control_panel_config)
            
            # Publish individual entities
            for property_name in partition_status:
                if property_name not in cfg.HOMEASSISTANT_PUBLISH_PARTITION_PROPERTIES:
                    continue
                partition_property_binary_sensor_config = self.entity_factory.make_partition_status_binary_sensor(partition, property_name)
                self._publish_config(partition_property_binary_sensor_config)

    def _publish_zone_configs(self, zone_statuses):
        for zone_key, zone_status in zone_statuses.items():
            if zone_key not in self.zones:
                continue

            zone = self.zones[zone_key]

            # Publish Status
            for property_name in zone_status:
                if property_name not in cfg.HOMEASSISTANT_PUBLISH_ZONE_PROPERTIES:
                    continue
                if property_name == "bypassed":
                    zone_status_sensor = self.entity_factory.make_zone_bypass_switch(zone)
                elif property_name == "signal_strength":
                    zone_status_sensor = self.entity_factory.make_zone_status_numeric_sensor(zone, property_name)
                else:
                    zone_status_sensor = self.entity_factory.make_zone_status_binary_sensor(zone, property_name)
                self._publish_config(zone_status_sensor)

    def _publish_pgm_configs(self, pgm_statuses):
        for pgm_key, pgm_status in pgm_statuses.items():
            if pgm_key not in self.pgms:
                continue

            pgm = self.pgms[pgm_key]

            pgm_switch_config = self.entity_factory.make_pgm_switch(pgm)
            self._publish_config(pgm_switch_config)
    
    def _publish_system_property_configs(self, system_statuses):
        for system_key, system_status in system_statuses.items():
            for property_name in system_status:
                system_property_config = self.entity_factory.make_system_status(system_key, property_name)
                self._publish_config(system_property_config)
