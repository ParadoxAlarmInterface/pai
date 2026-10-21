from paradox.interfaces.mqtt.entities.abstract_entity import AbstractControllableEntity
from paradox.lib.utils import sanitize_key


class Switch(AbstractControllableEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.hass_entity_type = "switch"

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
        self.property = "bypassed"

        self.pai_entity_type = "zone"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            payload_on="bypass",
            payload_off="clear_bypass",
        ))
        return config


class PGMSwitch(Switch):
    def __init__(self, pgm, device, availability_topic: str):
        super().__init__(device, availability_topic)
        self.pgm = pgm

        self.key = sanitize_key(pgm["key"])
        self.label = pgm["label"]
        self.property = "on"

        self.pai_entity_type = "pgm"


class ModulePGMSwitch(Switch):
    def __init__(self, module_pgm, device, availability_topic: str):
        super().__init__(device, availability_topic)
        self.module_pgm = module_pgm

        self.key = sanitize_key(module_pgm["key"])
        self.label = module_pgm["label"]
        self.property = "on"

        self.pai_entity_type = "pgm"

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            payload_on="on_override",
            payload_off="off_override",
        ))
        return config
