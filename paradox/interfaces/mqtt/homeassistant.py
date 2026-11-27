import asyncio
from collections import namedtuple
import json
import logging
import os

from paradox.config import config as cfg
from paradox.data.model import DetectedPanel
from paradox.lib import ps
from paradox.lib.utils import (
    SerializableToJSONEncoder,
    set_future_result_threadsafe,
)

from .core import AbstractMQTTInterface
from .entities.abstract_entity import AbstractEntity
from .entities.device import Device
from .entities.factory import MQTTAutodiscoveryEntityFactory

logger = logging.getLogger("PAI").getChild(__name__)

PreparseResponse = namedtuple("PreparseResponse", "topics element content")


def _load_discovery_topics(path):
    """Discovery topics published by the previous run, if they are known."""
    if not path:
        return set()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return set()
    except Exception as exc:
        logger.warning("Could not read discovery state %s: %s", path, exc)
        return set()

    return set(data.get("topics") or [])


def _save_discovery_topics(path, topics):
    """Remember the discovery topics of this run for the next cleanup."""
    if not path:
        return

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"topics": sorted(topics)}, f, indent=2)
    except OSError as exc:
        logger.warning("Could not write discovery state %s: %s", path, exc)


def stale_discovery_topics(previous, current):
    """Topics published before but no longer published."""
    return sorted(set(previous) - set(current))


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    republish_first = True  # discovery configs must precede states
    republish_state_delay = 2  # seconds for HA to subscribe to (re)created entities

    def __init__(self, alarm):
        super().__init__(alarm)
        self.armed = {}
        self.partitions = {}
        self.zones = {}
        self.pgms = {}
        self.module_pgms = {}

        self.entity_factory = MQTTAutodiscoveryEntityFactory(
            self.mqtt.availability_topic
        )

        self.run_status_topic = self.mqtt.pai_status_topic

        self._discovery_state_file = self._discovery_state_path()
        self._previous_discovery_topics = _load_discovery_topics(
            self._discovery_state_file
        )
        self._discovery_topics = set()

        self.connected_future = (
            asyncio.Future()
        )  # TODO: do not create it, use some other
        panel_detected_future = asyncio.Future()
        labels_loaded_future = asyncio.Future()
        first_status_update_future = asyncio.Future()

        def _ready_future_callback(x):
            self._publish_when_ready(
                panel_detected_future.result()["panel"],
                first_status_update_future.result()["status"],
            )

        ready_future = asyncio.ensure_future(
            asyncio.gather(
                self.connected_future,
                panel_detected_future,
                labels_loaded_future,
                first_status_update_future,
            )
        )
        ready_future.add_done_callback(_ready_future_callback)

        ps.subscribe(panel_detected_future, "panel_detected")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(labels_loaded_future, "labels_loaded")
        ps.subscribe(first_status_update_future, "status_update")

    def on_connect(self, client, userdata, connect_flags, reason_code, properties=None):
        self.subscribe_callback(
            f"{cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX}/status",
            self._handle_homeassistant_status,
        )
        # TODO: do not create connected_future, use some other
        set_future_result_threadsafe(self.connected_future, True)

    def _handle_homeassistant_status(self, client, userdata, message):
        # Home Assistant birth message: re-send discovery configs and states
        if message.payload.strip() == b"online":
            logger.info("Home Assistant came online")
            self.mqtt.republish_all()

    def republish_all(self, on_done=None):
        def delayed_done():
            if on_done:
                self.loop.call_later(self.republish_state_delay, on_done)

        super().republish_all(on_done=delayed_done)

    def _handle_labels_loaded(self, data):
        partitions = data.get("partition", {})
        for k, v in partitions.items():
            p_data = {}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data.get("zone", {})
        self.pgms = data.get("pgm", {})
        self.module_pgms = data.get("module_pgm", {})

    def _publish_when_ready(self, panel: DetectedPanel, status):
        self.entity_factory.set_device(Device(panel))

        self._publish_pai_state_sensor_config()

        if "partition" in status:
            self._publish_partition_configs(status["partition"])

        if "zone" in status:
            self._publish_zone_configs(status["zone"])

        if "pgm" in status:
            self._publish_pgm_configs(status["pgm"])

        module_pgms = dict(self.alarm.storage.get_container("module_pgm"))
        if module_pgms:
            self._publish_module_pgm_configs(module_pgms)

        self._publish_system_configs_from_status(status)

        if cfg.CONNECTION_TYPE == "PRT3" and cfg.PRT3_UTILITY_KEYS:
            self._publish_utility_key_configs(cfg.PRT3_UTILITY_KEYS)

        self._cleanup_stale_discovery_topics()

    def _discovery_state_path(self):
        """Where to remember published discovery topics between runs."""
        location = cfg.CONFIG_FILE_LOCATION
        if not isinstance(location, str) or not location:
            return None

        return os.path.join(
            os.path.dirname(os.path.abspath(location)), "pai_discovery.json"
        )

    def _cleanup_stale_discovery_topics(self):
        """Remove discovery topics this run no longer publishes.

        Without this a zone whose type changes keeps its old entities in Home
        Assistant, because the retained discovery message is never cleared.
        """
        stale = stale_discovery_topics(
            self._previous_discovery_topics, self._discovery_topics
        )
        if not self._discovery_topics:
            # Publishing failed or the panel reported nothing; removing every
            # remembered topic would delete working entities.
            logger.warning("No discovery topics published, skipping cleanup")
            return

        for topic in stale:
            logger.info("Removing stale discovery topic %s", topic)
            self.publish(topic, "", 0, True)

        _save_discovery_topics(self._discovery_state_file, self._discovery_topics)
        self._previous_discovery_topics = set(self._discovery_topics)

    def _publish_config(self, entity: AbstractEntity):
        self._discovery_topics.add(entity.configuration_topic)
        self.publish(
            entity.configuration_topic,
            json.dumps(entity, cls=SerializableToJSONEncoder),
            0,
            cfg.MQTT_RETAIN,
        )

    def _publish_pai_state_sensor_config(self):
        pai_state_sensor_config = self.entity_factory.make_pai_status_sensor(
            self.run_status_topic
        )
        self._publish_config(pai_state_sensor_config)

    def _publish_partition_configs(self, partition_statuses):
        for partition_key, partition_status in partition_statuses.items():
            if partition_key not in self.partitions:
                continue

            partition = self.partitions[partition_key]
            code = (
                cfg.MQTT_HOMEASSISTANT_CODE or None
            )  # returns None on empty string. For HA Addon Schema parsing

            partition_alarm_control_panel_config = (
                self.entity_factory.make_alarm_control_panel_config(partition, code)
            )
            self._publish_config(partition_alarm_control_panel_config)

            # Publish individual entities
            for property_name in partition_status:
                if property_name not in cfg.HOMEASSISTANT_PUBLISH_PARTITION_PROPERTIES:
                    continue

                partition_property_binary_sensor_config = (
                    self.entity_factory.make_partition_status_binary_sensor(
                        partition, property_name
                    )
                )
                self._publish_config(partition_property_binary_sensor_config)

    def _publish_zone_configs(self, zone_statuses):
        for zone_key, zone_status in zone_statuses.items():
            if zone_key not in self.zones:
                continue

            zone = self.zones[zone_key]

            # Publish Status
            published_properties = {
                name
                for name in zone_status
                if name in cfg.HOMEASSISTANT_PUBLISH_ZONE_PROPERTIES
            }
            for property_name in zone_status:
                if property_name not in published_properties:
                    continue

                if property_name == "bypassed":
                    zone_status_sensor = self.entity_factory.make_zone_bypass_switch(
                        zone
                    )
                elif property_name == "signal_strength":
                    zone_status_sensor = (
                        self.entity_factory.make_zone_status_numeric_sensor(
                            zone, property_name
                        )
                    )
                else:
                    zone_status_sensor = (
                        self.entity_factory.make_zone_status_binary_sensor(
                            zone, property_name, published_properties
                        )
                    )

                self._publish_config(zone_status_sensor)

    def _publish_pgm_configs(self, pgm_statuses):
        for pgm_key in pgm_statuses:
            if pgm_key not in self.pgms:
                continue

            pgm = self.pgms[pgm_key]

            pgm_switch_config = self.entity_factory.make_pgm_switch(pgm)
            self._publish_config(pgm_switch_config)

    def _publish_module_pgm_configs(self, module_pgms):
        for _, module_pgm in module_pgms.items():
            module_pgm_switch_config = self.entity_factory.make_module_pgm_switch(
                module_pgm
            )
            self._publish_config(module_pgm_switch_config)

    def _publish_system_configs_from_status(self, status):
        system_statuses = {}

        if "system" in status:
            system_statuses.update(status["system"])

        # In the PAI status_update payload, troubles are exposed as a top-level
        # branch, while the MQTT state publisher exposes them under:
        #
        #   paradox/states/system/troubles/...
        #
        # Re-wrap them here so Home Assistant discovery matches the existing
        # MQTT state topic convention:
        #
        #   status["troubles"]["ac_failure_trouble"]
        #   -> system_troubles_ac_failure_trouble
        #   -> paradox/states/system/troubles/ac_failure_trouble
        if "troubles" in status:
            system_statuses["troubles"] = status["troubles"]

        if system_statuses:
            self._publish_system_property_configs(system_statuses)

    def _publish_system_property_configs(self, system_statuses):
        excluded = set(cfg.HOMEASSISTANT_EXCLUDE_SYSTEM_PROPERTIES)
        for system_key, system_status in system_statuses.items():
            if system_key in excluded:
                continue
            for property_name in system_status:
                if f"{system_key}/{property_name}" in excluded:
                    continue
                system_property_config = self.entity_factory.make_system_status(
                    system_key, property_name
                )
                self._publish_config(system_property_config)

    def _publish_utility_key_configs(self, utility_keys: dict):
        """Publish HA button discovery configs for PRT3 utility keys.

        ``utility_keys`` is ``{key_num: label}`` from ``PRT3_UTILITY_KEYS``.
        Only keys explicitly listed in config are published; the full 1-251
        range is not auto-discovered because utility key actions are
        panel-programmed and have no introspectable meaning.
        """
        for key_num, label in utility_keys.items():
            try:
                key_num = int(key_num)
            except (ValueError, TypeError):
                logger.warning(
                    "PRT3_UTILITY_KEYS: invalid key number %r, skipping", key_num
                )
                continue

            if not 1 <= key_num <= 251:
                logger.warning(
                    "PRT3_UTILITY_KEYS: key number %d out of range (expected 1..251), skipping",
                    key_num,
                )
                continue

            button = self.entity_factory.make_utility_key_button(key_num, str(label))
            self._publish_config(button)
