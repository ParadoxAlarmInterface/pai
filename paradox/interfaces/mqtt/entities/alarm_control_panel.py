from paradox.interfaces.mqtt.entities.abstract_entity import AbstractControllableEntity
from paradox.interfaces.mqtt.entities.device import Device
from paradox.lib.utils import sanitize_key


class AlarmControlPanel(AbstractControllableEntity):
    def __init__(self, partition: dict, device: Device, availability_topic: str, code: str = None):
        super(AlarmControlPanel, self).__init__(device, availability_topic)

        self.key = sanitize_key(partition["key"])
        self.label = partition["label"]
        self.property = "current_state"

        self.hass_entity_type = "alarm_control_panel"
        self.pai_entity_type = "partition"

        self.code = code

    def serialize(self):
        config = super().serialize()
        config.update(dict(
            payload_disarm="disarm",
            payload_arm_home="arm_stay",
            payload_arm_away="arm",
            payload_arm_night="arm_sleep"
        ))
        if self.code is not None:
            config['code']=self.code
        else:
            config.update(dict(
                code_arm_required=False,
                code_disarm_required=False,
                code_trigger_required=False
            ))
        return config

    @property
    def entity_id(self):
        return f"{self.pai_entity_type}_{self.key.lower()}"

    @property
    def entity_name(self):
        return f"{self.pai_entity_type.title()} {self.label}"