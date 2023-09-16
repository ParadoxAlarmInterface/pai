from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.lib.utils import sanitize_key


class PAIStatusSensor(AbstractEntity):
    def __init__(self, run_status_topic, device, availability_topic):
        super().__init__(device, availability_topic)

        self.hass_entity_type = "sensor"

        self.run_status_topic = run_status_topic

    def serialize(self):
        config = super().serialize()

        del config["availability_topic"]

        return config

    @property
    def state_topic(self):
        return self.run_status_topic

    @property
    def entity_id(self):
        return "pai_status"

    @property
    def entity_name(self):
        return "PAI Status"


class ZoneNumericSensor(AbstractEntity):
    def __init__(self, entity, property, device, availability_topic):
        super().__init__(device, availability_topic)

        self.property = property
        self.label = entity.get("label", entity["key"].replace("_", " "))

        self.key = sanitize_key(entity["key"])

        self.pai_entity_type = "zone"
        self.hass_entity_type = "sensor"


class SystemStatusSensor(AbstractEntity):
    def __init__(self, key, property, device, availability_topic):
        super().__init__(device, availability_topic)

        self.property = property
        self.label = key.replace("_", " ").title()

        self.key = sanitize_key(key)

        self.pai_entity_type = "system"
        self.hass_entity_type = "sensor"

    def serialize(self):
        config = super().serialize()
        if self.key == 'power':
            config['unit_of_measurement'] = 'V'

        return config