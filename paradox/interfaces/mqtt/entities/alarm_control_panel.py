from paradox.interfaces.mqtt.entities.abstract_entity import AbstractEntity
from paradox.interfaces.mqtt.entities.device import Device
from paradox.lib.utils import sanitize_key
from paradox.config import config as cfg


class AlarmControlPanel(AbstractEntity):
    def __init__(self, partition: dict, device: Device, availability_topic: str):
        super(AlarmControlPanel, self).__init__(device, availability_topic)

        self.key = sanitize_key(partition["key"])
        self.label = partition["label"]

    def get_configuration_topic(self):
        return "{}/alarm_control_panel/{}/partition_{}/config".format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
            self.device.serial_number,
            self.key
        )

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            name=f'Paradox {self.device.serial_number} Partition {self.label}',
            unique_id=f'paradox_{self.device.serial_number}_partition_{self.key.lower()}',
            command_topic=self._get_command_topic(),
            state_topic=self._get_state_topic(),
            payload_disarm="disarm",
            payload_arm_home="arm_stay",
            payload_arm_away="arm",
            payload_arm_night="arm_sleep"
        ))
        return config

    def _get_state_topic(self):
        return "{}/{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_STATES_TOPIC,
            cfg.MQTT_PARTITION_TOPIC,
            self.key,
            "current_state",
        )

    def _get_command_topic(self):
        return "{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_CONTROL_TOPIC,
            cfg.MQTT_PARTITION_TOPIC,
            self.key
        )