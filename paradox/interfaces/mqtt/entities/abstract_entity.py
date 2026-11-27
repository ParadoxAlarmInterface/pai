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
        # Properties published for this entity's zone. Used to tell a zone
        # with a single thing to report from one with several.
        self.zone_properties = frozenset()

    @property
    def entity_id(self):
        return f"{self._typed_key()}_{self.property}"

    def _typed_key(self) -> str:
        """Key prefixed with the entity type, without repeating the prefix.

        Partition keys come from their display name, so a default partition
        key already reads "partition_1"; prefixing it again would produce
        "partition_partition_1" in unique_ids and discovery topics.
        """
        key = self.key.lower()
        prefix = f"{self.pai_entity_type}_"
        if (
            self.pai_entity_type == "partition"
            and cfg.DIGIPLEX_PARTITION_NAMES
            and key.startswith(prefix)
        ):
            return key
        return prefix + key

    @property
    def zone_naming(self) -> dict:
        """Per-zone display overrides from the ``ZONE_NAMES`` config option.

        Zones listed there get their own device name and property names, so
        one zone can be named in any language without touching the code.
        """
        if self.pai_entity_type != "zone":
            return {}

        naming = (cfg.ZONE_NAMES or {}).get(self.key)
        return naming if isinstance(naming, dict) else {}

    @property
    def entity_name(self):
        naming = self.zone_naming
        if naming:
            # The zone already has its own device named after the object, so
            # repeating it here would show the name twice. ``None`` means the
            # entity is the device's main feature and takes its name.
            if self.property in naming:
                # Empty (or null) means the entity takes the device name.
                return naming[self.property] or ""

            if self.property in ("open", "tamper"):
                # Let Home Assistant name the entity from its device class, so
                # the name follows the Home Assistant language (motion ->
                # Judesys, tamper -> Tamperis, ...). A zone with a single thing
                # to report takes the device name instead of repeating it.
                if self.property == "tamper" or len(self.zone_properties) > 1:
                    return None
                return ""

            return to_label(self.property)

        if self.pai_entity_type == "system":
            name = (cfg.SYSTEM_NAMES or {}).get(f"{self.key}_{self.property}")
            if name is not None:
                return name

        label = self.label or to_label(self.key)

        return f"{self.pai_entity_type.title()} {label} {to_label(self.property)}"

    @property
    def default_entity_id(self):
        """Entity id for newly discovered entities, if it has to be set.

        ``None`` leaves the id to Home Assistant, which derives it from the
        entity name. Zones with explicit names get a short, stable id
        (``binary_sensor.<zone>_<property>``) that does not repeat the label.
        """
        if self.pai_entity_type != "zone" or not self.zone_naming:
            return None

        return f"{self.hass_entity_type}.{self.key.lower()}_{self.property}"

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

        naming = self.zone_naming
        device = dict(
            identifiers=[f"Paradox_{self.device.serial_number}_zone_{self.key}"],
            name=naming.get("name") or self.label or to_label(self.key),
            manufacturer="Paradox",
            model="Zone",
            via_device=self.device.serialize()["identifiers"][0],
        )
        if naming.get("area"):
            # Home Assistant only uses this when the device is created.
            device["suggested_area"] = naming["area"]

        return device

    def serialize(self):
        prefix = cfg.MQTT_HOMEASSISTANT_ENTITY_PREFIX.format_map(
            {
                "serial_number": self.device.serial_number,
                "model": self.device.model,
            }
        )
        config = dict(
            availability_topic=self.availability_topic,
            device=self._hass_device(),
            unique_id=f"paradox_{self.device.serial_number}_{self.entity_id}",
            state_topic=self.state_topic,
        )
        # An empty name is meaningful: the entity is the device's main feature
        # and Home Assistant shows just the device name. Omitting the key does
        # not work, because a binary sensor with a device class is then named
        # after the class, which repeats the device name.
        name = self.entity_name
        if name is not None:
            config["name"] = (prefix + name) if name else ""

        default_entity_id = self.default_entity_id
        if default_entity_id:
            config["default_entity_id"] = default_entity_id

        return config

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
