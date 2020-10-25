from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.lib.utils import sanitize_key
from paradox.config import config as cfg


class AbstractBinarySensor(AbstractEntity):
    SENSOR_TYPE = "binary_sensor"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            payload_on="True",
            payload_off="False",
        ))
        return config


class AbstractStatusBinarySensor(AbstractBinarySensor):
    def __init__(self, entity, property_name: str, device, availability_topic: str):
        super().__init__(device, availability_topic)

        self.label = entity.get("label", entity["key"])
        self.property_name = property_name

        self.key = sanitize_key(entity["key"])

    @property
    def entity_type(self) -> str:
        raise NotImplemented()

    def get_configuration_topic(self):
        return f"{cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX}/{self.SENSOR_TYPE}/{self.device.serial_number}/{self.entity_type}_{self.key}_{self.property_name}/config"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            name=f'Paradox {self.device.serial_number} {self.entity_type.capitalize()} {self.label} {self.property_name.replace("_", " ").capitalize()}',
            unique_id=f'paradox_{self.device.serial_number}_{self.entity_type}_{self.key.lower()}_{self.property_name}',
            state_topic=self._get_state_topic(),
        ))
        return config

    def _get_state_topic(self):
        return "{}/{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_STATES_TOPIC,
            getattr(cfg, f"MQTT_{self.entity_type.upper()}_TOPIC"),
            self.key,
            self.property_name,
        )


class PartitionBinarySensor(AbstractStatusBinarySensor):
    @property
    def entity_type(self) -> str:
        return "partition"


class ZoneStatusBinarySensor(AbstractStatusBinarySensor):
    @property
    def entity_type(self) -> str:
        return "zone"

    def serialize(self):
        config = super().serialize()
        if self.property_name == 'open':
            config['device_class'] = 'motion'

        return config


class SystemBinarySensor(AbstractStatusBinarySensor):
    def __init__(self, key: str, property_name: str, device, availability_topic: str):
        super().__init__({"key": key}, property_name, device, availability_topic)

    @property
    def entity_type(self) -> str:
        return "system"
