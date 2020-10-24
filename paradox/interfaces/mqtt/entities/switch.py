from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.config import config as cfg
from paradox.lib.utils import sanitize_key


class Switch(AbstractEntity):
    @property
    def entity_type(self) -> str:
        raise NotImplemented()

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            state_on="True",
            state_off="False",
        ))
        return config


class ZoneBypassSwitch(Switch):
    def __init__(self, zone, device, availability_topic: str):
        super().__init__(device, availability_topic)
        self.zone = zone

        self.key = sanitize_key(zone["key"])
        self.label = zone["label"]

    @property
    def entity_type(self) -> str:
        return "zone"

    def get_configuration_topic(self):
        return f"{cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX}/switch/{self.device.serial_number}/{self.entity_type}_{self.key}_bypass/config"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            name=f'Zone {self.label} Bypass',
            unique_id=f'paradox_{self.device.serial_number}_zone_{self.key.lower()}_bypass',
            state_topic=self._get_state_topic(),
            command_topic=self._get_command_topic(),
            payload_on="bypass",
            payload_off="clear_bypass",
        ))
        return config

    def _get_command_topic(self):
        return "{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_CONTROL_TOPIC,
            cfg.MQTT_ZONE_TOPIC,
            self.key,
        )

    def _get_state_topic(self):
        return "{}/{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_STATES_TOPIC,
            cfg.MQTT_ZONE_TOPIC,
            self.key,
            "bypassed",
        )


class PGMSwitch(Switch):
    def __init__(self, pgm, device, availability_topic: str):
        super().__init__(device, availability_topic)
        self.pgm = pgm

        self.key = sanitize_key(pgm["key"])

    @property
    def entity_type(self) -> str:
        return "pgm"

    def get_configuration_topic(self):
        return f"{cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX}/switch/{self.device.serial_number}/{self.entity_type}_{self.key}_open/config"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            name=f'PGM {self.pgm["label"]} Open',
            unique_id=f'paradox_{self.device.serial_number}_pgm_{self.key.lower()}_open',
            state_topic=self._get_state_topic(),
            command_topic=self._get_command_topic(),
        ))
        return config

    def _get_command_topic(self):
        return "{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_CONTROL_TOPIC,
            cfg.MQTT_OUTPUT_TOPIC,
            self.key
        )

    def _get_state_topic(self):
        return "{}/{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_STATES_TOPIC,
            cfg.MQTT_OUTPUT_TOPIC,
            self.key,
            "on",
        )