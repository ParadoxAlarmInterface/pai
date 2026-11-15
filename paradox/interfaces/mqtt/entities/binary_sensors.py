import logging

from paradox.config import config as cfg
from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.lib.utils import sanitize_key

logger = logging.getLogger("PAI").getChild(__name__)

# Home Assistant binary_sensor device classes accepted in ZONE_DEVICE_CLASS.
ZONE_DEVICE_CLASSES = (
    "motion",
    "door",
    "window",
    "garage_door",
    "smoke",
    "vibration",
    "tamper",
    "gas",
    "moisture",
    "occupancy",
    "opening",
    "safety",
    "problem",
)
DEFAULT_ZONE_DEVICE_CLASS = "motion"


def zone_device_class(zone_key: str) -> str:
    """Zone key -> Home Assistant device_class from ``ZONE_DEVICE_CLASS``.

    Panels do not expose the physical sensor type (zone definitions describe
    behaviour only), so the mapping is explicit configuration. Unlisted zones
    and unknown classes fall back to "motion".
    """
    device_class = (cfg.ZONE_DEVICE_CLASS or {}).get(zone_key, DEFAULT_ZONE_DEVICE_CLASS)
    if device_class not in ZONE_DEVICE_CLASSES:
        logger.warning(
            "Ignoring unknown device_class %r for zone %r, using %r",
            device_class,
            zone_key,
            DEFAULT_ZONE_DEVICE_CLASS,
        )
        return DEFAULT_ZONE_DEVICE_CLASS

    return device_class


class AbstractStatusBinarySensor(AbstractEntity):
    def __init__(self, entity, property: str, device, availability_topic: str):
        super().__init__(device, availability_topic)

        self.label = entity.get("label", entity["key"].replace("_", " "))
        self.property = property

        self.key = sanitize_key(entity["key"])

        self.hass_entity_type = "binary_sensor"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            payload_on="True",
            payload_off="False",
        ))
        return config


class PartitionBinarySensor(AbstractStatusBinarySensor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.pai_entity_type = "partition"


class ZoneStatusBinarySensor(AbstractStatusBinarySensor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.pai_entity_type = "zone"

    def serialize(self):
        config = super().serialize()
        if self.property == 'open':
            config['device_class'] = zone_device_class(self.key)

        return config


class SystemBinarySensor(AbstractStatusBinarySensor):
    def __init__(self, key: str, property: str, device, availability_topic: str):
        super().__init__({"key": key}, property, device, availability_topic)

        self.pai_entity_type = "system"
