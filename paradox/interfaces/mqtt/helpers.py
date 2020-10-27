from paradox.config import config as cfg

ELEMENT_TOPIC_MAP = dict(
    partition=cfg.MQTT_PARTITION_TOPIC,
    zone=cfg.MQTT_ZONE_TOPIC,
    output=cfg.MQTT_OUTPUT_TOPIC,
    pgm=cfg.MQTT_OUTPUT_TOPIC,
    repeater=cfg.MQTT_REPEATER_TOPIC,
    bus=cfg.MQTT_BUS_TOPIC,
    module=cfg.MQTT_MODULE_TOPIC,
    keypad=cfg.MQTT_KEYPAD_TOPIC,
    system=cfg.MQTT_SYSTEM_TOPIC,
    user=cfg.MQTT_USER_TOPIC,
    door=cfg.MQTT_DOOR_TOPIC,
)


def get_control_topic_prefix(element_type):
    return "/".join([
        cfg.MQTT_BASE_TOPIC,
        cfg.MQTT_CONTROL_TOPIC,
        ELEMENT_TOPIC_MAP[element_type],
    ])


def get_state_topic_prefix(element_type):
    return "/".join([
        cfg.MQTT_BASE_TOPIC,
        cfg.MQTT_STATES_TOPIC,
        ELEMENT_TOPIC_MAP[element_type],
    ])