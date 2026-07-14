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

    def _hass_device(self):
        """Device block for the discovery payload.

        Zones get their own device, linked to the panel with ``via_device`` so
        Home Assistant nests them underneath it. Without this every zone sensor,
        binary sensor and bypass switch lands on the panel device, which on a
        large system is a flat list of hundreds of entities.

        ``unique_id`` is deliberately untouched, so on an existing install the
        entities are re-parented in place: entity ids, customisations and
        history are all preserved.
        """
        if self.pai_entity_type != "zone":
            return self.device

        return dict(
            identifiers=[f"Paradox_{self.device.serial_number}_zone_{self.key}"],
            name=self.label or to_label(self.key),
            manufacturer="Paradox",
            model="Zone",
            via_device=self.device.serialize()["identifiers"][0],
        )

    def serialize(self):
        prefix = cfg.MQTT_HOMEASSISTANT_ENTITY_PREFIX.format_map(
            {
                "serial_number": self.device.serial_number,
                "model": self.device.model,
            }
        )
        return dict(
            availability_topic=self.availability_topic,
            device=self._hass_device(),
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
