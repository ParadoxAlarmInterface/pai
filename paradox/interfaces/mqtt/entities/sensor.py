from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.config import config as cfg
from paradox.lib.utils import sanitize_key


class PAIStatusSensor(AbstractEntity):
    def __init__(self, run_status_topic, device, availability_topic):
        super().__init__(device, availability_topic)

        self.run_status_topic = run_status_topic

    def get_configuration_topic(self):
        return "{}/sensor/{}/{}/config".format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX, self.device.serial_number, "pai_status"
        )

    def serialize(self):
        config = dict(
            name=f'Paradox {self.device.serial_number} PAI Status',
            unique_id=f'paradox_{self.device.serial_number}_pai_status',
            state_topic=self.run_status_topic,
            device=self.device
        )
        return config


class SystemStatusSensor(AbstractEntity):
    def __init__(self, key, property_name, device, availability_topic):
        super().__init__(device, availability_topic)

        self.property_name = property_name

        self.key = sanitize_key(key)

    def get_configuration_topic(self):
        return "{}/sensor/{}/system_{}_{}/config".format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
            self.device.serial_number,
            self.key,
            self.property_name
        )

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            name=f'Paradox {self.device.serial_number} System {self.key.title()} {self.property_name.replace("_", " ").title()}',
            unique_id=f'paradox_{self.device.serial_number}_system_{self.key}_{self.property_name}',
            state_topic=self._get_state_topic(),
        ))
        if self.key == 'power':
            config['unit_of_measurement'] = 'V'

        return config

    def _get_state_topic(self):
        return "{}/{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_STATES_TOPIC,
            cfg.MQTT_SYSTEM_TOPIC,
            self.key,
            self.property_name,
        )