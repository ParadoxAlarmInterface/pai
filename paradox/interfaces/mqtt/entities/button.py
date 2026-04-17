from paradox.config import config as cfg
from paradox.interfaces.mqtt.entities.device import Device


class UtilityKeyButton:
    """HA MQTT button entity for a PRT3 utility key.

    Buttons are stateless — there is no state_topic.  Pressing the button in
    HA publishes ``payload_press`` to the command_topic, which the
    ``_mqtt_handle_utility_key`` subscriber picks up and forwards to the panel.

    PRT3 limitation: utility keys have no persistent state and no feedback
    channel (the panel echoes &OK/&fail but that is not surfaced as HA state).
    """

    hass_entity_type = "button"

    def __init__(
        self,
        key_num: int,
        label: str,
        device: Device,
        availability_topic: str,
    ):
        self.device = device
        self.availability_topic = availability_topic
        self.key_num = key_num
        self.label = label or f"Utility Key {key_num}"

    @property
    def entity_id(self) -> str:
        return f"utility_key_{self.key_num}"

    @property
    def configuration_topic(self) -> str:
        return "/".join(
            [
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                self.hass_entity_type,
                self.device.serial_number,
                self.entity_id,
                "config",
            ]
        )

    @property
    def command_topic(self) -> str:
        return "{}/{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC,
            cfg.MQTT_CONTROL_TOPIC,
            cfg.MQTT_UTILITY_KEY_TOPIC,
            self.key_num,
        )

    def serialize(self) -> dict:
        prefix = cfg.MQTT_HOMEASSISTANT_ENTITY_PREFIX.format_map(
            {
                "serial_number": self.device.serial_number,
                "model": self.device.model,
            }
        )
        return dict(
            availability_topic=self.availability_topic,
            device=self.device,
            name=prefix + self.label,
            unique_id=f"paradox_{self.device.serial_number}_{self.entity_id}",
            command_topic=self.command_topic,
            payload_press="trigger",
        )
