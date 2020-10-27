from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.lib.utils import sanitize_key


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
            config['device_class'] = 'motion'

        return config


class SystemBinarySensor(AbstractStatusBinarySensor):
    def __init__(self, key: str, property: str, device, availability_topic: str):
        super().__init__({"key": key}, property, device, availability_topic)

        self.pai_entity_type = "system"
