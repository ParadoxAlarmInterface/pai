from paradox.config import config as cfg
from paradox.interfaces.mqtt.entities.device import Device
from paradox.interfaces.mqtt.helpers import (
    get_control_topic_prefix,
    get_state_topic_prefix,
)


def to_label(txt):
    return txt.replace("_", " ").title()


class AbstractEntity:
    def __init__(self, device: Device, availability_topic):
        self.availability_topic = availability_topic
        self.device = device

        self.pai_entity_type: str = None
        self.hass_entity_type: str = None

        self.key: str = None
        self.property: str = None
        self.label: str = None

    @property
    def entity_id(self):
        return f"{self.pai_entity_type}_{self.key.lower()}_{self.property}"

    @property
    def entity_name(self):
        label = self.label or to_label(self.key)

        return f"{self.pai_entity_type.title()} {label} {to_label(self.property)}"

    @property
    def configuration_topic(self):
        return "/".join(
            [
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                self.hass_entity_type,
                self.device.serial_number,
                self.entity_id,
                "config",
            ]
        )

    def serialize(self):
        prefix = cfg.MQTT_HOMEASSISTANT_ENTITY_PREFIX.format(
            {
                "serial_number",
                self.device.serial_number,
                "model",
                self.device.model,
            }
        )
        return dict(
            availability_topic=self.availability_topic,
            device=self.device,
            name=prefix + f"{self.entity_name}",
            unique_id=f"paradox_{self.device.serial_number}_{self.entity_id}",
            state_topic=self.state_topic,
        )

    @property
    def command_topic(self):
        prefix = get_control_topic_prefix(self.pai_entity_type)
        return f"{prefix}/{self.key}"

    @property
    def state_topic(self):
        prefix = get_state_topic_prefix(self.pai_entity_type)
        return f"{prefix}/{self.key}/{self.property}"


class AbstractControllableEntity(AbstractEntity):
    def serialize(self):
        config = super().serialize()
        config.update(dict(command_topic=self.command_topic))
        return config
