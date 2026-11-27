import json

import pytest
import pytest_asyncio

from paradox.config import config as cfg
from paradox.data.model import DetectedPanel
from paradox.interfaces.mqtt.entities.device import Device
from paradox.interfaces.mqtt.entities.factory import MQTTAutodiscoveryEntityFactory
from paradox.lib.utils import SerializableToJSONEncoder


@pytest_asyncio.fixture
def mqtt_entity_factory():
    return MQTTAutodiscoveryEntityFactory("paradox/interface/availability", _make_device())


def test_alarm_control_panel_serialize(mqtt_entity_factory):
    alarm_control_panel = mqtt_entity_factory.make_alarm_control_panel_config({"key": "Partition_1", "label": "Partition 1"})
    assert _serialize_deserialize(alarm_control_panel) == {
        'unique_id': 'paradox_1234abcd_partition_partition_1',
        'name': 'Partition Partition 1',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/partitions/Partition_1/current_state',
        'command_topic': 'paradox/control/partitions/Partition_1',
        'device': _get_expected_device_block(),
        'payload_arm_away': 'arm',
        'payload_arm_home': 'arm_stay',
        'payload_arm_night': 'arm_sleep',
        'payload_disarm': 'disarm',
        'code_arm_required': False,
        'code_disarm_required': False,
        'code_trigger_required': False
    }

    assert alarm_control_panel.configuration_topic == "homeassistant/alarm_control_panel/1234abcd/partition_partition_1/config"


def test_alarm_control_panel_serialize_with_partition_names(mqtt_entity_factory, monkeypatch):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {1: "House"})

    alarm_control_panel = mqtt_entity_factory.make_alarm_control_panel_config({"key": "Partition_1", "label": "Partition 1"})

    assert _serialize_deserialize(alarm_control_panel)["unique_id"] == "paradox_1234abcd_partition_1"
    assert _serialize_deserialize(alarm_control_panel)["name"] == "Partition 1"
    assert alarm_control_panel.configuration_topic == "homeassistant/alarm_control_panel/1234abcd/partition_1/config"


def test_partition_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_partition_status_binary_sensor({"key": "Partition_1", "label": "Partition 1"}, "arm")
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_partition_partition_1_arm',
        'name': 'Partition Partition 1 Arm',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/partitions/Partition_1/arm',
        'device': _get_expected_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
    }

    assert binary_sensor.configuration_topic == "homeassistant/binary_sensor/1234abcd/partition_partition_1_arm/config"


def test_partition_binary_sensor_serialize_with_partition_names(mqtt_entity_factory, monkeypatch):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {1: "House"})

    binary_sensor = mqtt_entity_factory.make_partition_status_binary_sensor({"key": "Partition_1", "label": "Partition 1"}, "arm")

    config = _serialize_deserialize(binary_sensor)
    assert config["unique_id"] == "paradox_1234abcd_partition_1_arm"
    assert config["name"] == "Partition 1 Arm"


def test_zone_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "open", properties={"open"}
    )
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_zone_zone_1_open',
        'name': 'Zone Zone 1 Open',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/zones/Zone_1/open',
        'device': _get_expected_zone_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
        'device_class': 'motion'
    }

    assert binary_sensor.configuration_topic == "homeassistant/binary_sensor/1234abcd/zone_zone_1_open/config"


@pytest.mark.parametrize(
    ("mapping", "expected"),
    [
        ({"fasado_durys": "door"}, "door"),
        ({"fasado_durys": "garage_door"}, "garage_door"),
        ({"other": "door"}, "motion"),
        ({"fasado_durys": "not_a_device_class"}, "motion"),
    ],
)
def test_zone_binary_sensor_device_class(mqtt_entity_factory, monkeypatch, mapping, expected):
    monkeypatch.setattr(cfg, "ZONE_DEVICE_CLASS", mapping)
    monkeypatch.setattr(cfg, "ZONE_TYPES", ["dummy=motion"])
    zone = {"key": "fasado_durys", "label": "fasado durys"}

    open_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(zone, "open")
    tamper_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(zone, "tamper")

    assert open_sensor.serialize()["device_class"] == expected
    assert tamper_sensor.serialize()["device_class"] == "tamper"


def test_zone_with_multiple_properties_uses_device_class_name(mqtt_entity_factory, monkeypatch):
    monkeypatch.setattr(cfg, "ZONE_NAMES", {"Zone_1": {"name": "Zone 1"}})
    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "open", properties={"open", "tamper"}
    )
    config = _serialize_deserialize(binary_sensor)
    # No name key: Home Assistant names it from the device class in its own
    # language.
    assert "name" not in config
    assert config["device_class"] == "motion"
    assert config["default_entity_id"] == "binary_sensor.zone_1_open"

    tamper = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "tamper", properties={"open", "tamper"}
    )
    tamper_config = _serialize_deserialize(tamper)
    assert "name" not in tamper_config
    assert tamper_config["device_class"] == "tamper"
    assert tamper_config["default_entity_id"] == "binary_sensor.zone_1_tamper"


def test_trouble_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_system_status("troubles", "ac_trouble")
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_system_troubles_ac_trouble',
        'name': 'System troubles Ac Trouble',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/system/troubles/ac_trouble',
        'device': _get_expected_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
    }

    assert binary_sensor.configuration_topic == "homeassistant/binary_sensor/1234abcd/system_troubles_ac_trouble/config"


def test_pai_status_sensor_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_pai_status_sensor("paradox/interface/pai_status")
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_pai_status',
        'name': 'PAI Status',
        'state_topic': 'paradox/interface/pai_status',
        'device': _get_expected_device_block()
    }

    assert sensor.configuration_topic == "homeassistant/sensor/1234abcd/pai_status/config"


def test_run_system_status_sensor_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_system_status("power", "vdc")
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_system_power_vdc',
        'name': 'System Power Vdc',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/system/power/vdc',
        'device': _get_expected_device_block(),
        'unit_of_measurement': 'V'
    }

    assert sensor.configuration_topic == "homeassistant/sensor/1234abcd/system_power_vdc/config"


def test_pgm_switch_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_pgm_switch({"key": "PGM_1", "label": "PGM 1"})
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_pgm_pgm_1_on',
        'name': 'Pgm PGM 1 On',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/outputs/PGM_1/on',
        'command_topic': 'paradox/control/outputs/PGM_1',
        'device': _get_expected_device_block(),
        'state_on': 'True',
        'state_off': 'False',
    }

    assert sensor.configuration_topic == "homeassistant/switch/1234abcd/pgm_pgm_1_on/config"


def test_zone_bypass_switch_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_zone_bypass_switch({"key": "Zone_1", "label": "Zone 1"})
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_zone_zone_1_bypassed',
        'name': 'Zone Zone 1 Bypassed',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/zones/Zone_1/bypassed',
        'command_topic': 'paradox/control/zones/Zone_1',
        'device': _get_expected_zone_device_block(),
        'state_on': 'True',
        'state_off': 'False',
        'payload_on': 'bypass',
        'payload_off': 'clear_bypass',
    }

    assert sensor.configuration_topic == "homeassistant/switch/1234abcd/zone_zone_1_bypassed/config"


def test_zone_bypass_switch_serialize_with_naming(mqtt_entity_factory, monkeypatch):
    monkeypatch.setattr(cfg, "ZONE_NAMES", {"Zone_1": {"name": "Garage"}})

    sensor = mqtt_entity_factory.make_zone_bypass_switch({"key": "Zone_1", "label": "Zone 1"})
    config = _serialize_deserialize(sensor)
    assert config["name"] == "Bypass"
    assert config["default_entity_id"] == "switch.zone_1_bypassed"


def test_zone_naming_overrides_from_config(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(
        cfg,
        "ZONE_NAMES",
        {
            "Zone_1": {
                "name": "Garage",
                "area": "garage",
                "open": "Motion",
                "tamper": "Tamper",
            }
        },
    )

    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1", "device_class": "motion"}, "open"
    )
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_zone_zone_1_open',
        'name': 'Motion',
        'default_entity_id': 'binary_sensor.zone_1_open',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/zones/Zone_1/open',
        'device': {
            'identifiers': ['Paradox_1234abcd_zone_Zone_1'],
            'manufacturer': 'Paradox',
            'model': 'Zone',
            'name': 'Garage',
            'suggested_area': 'garage',
            'via_device': 'Paradox_1234abcd',
        },
        'payload_on': 'True',
        'payload_off': 'False',
        'device_class': 'motion',
    }

    tamper = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1", "device_class": "motion"}, "tamper"
    )
    tamper_config = _serialize_deserialize(tamper)
    assert tamper_config["name"] == "Tamper"
    assert tamper_config["default_entity_id"] == "binary_sensor.zone_1_tamper"


def test_zone_naming_uses_device_name_for_single_feature(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "ZONE_NAMES", {"Zone_1": {"name": "Garage"}})

    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "open"
    )
    config = _serialize_deserialize(binary_sensor)
    assert config["name"] == ""
    assert config["default_entity_id"] == "binary_sensor.zone_1_open"
    assert "suggested_area" not in config["device"]


def test_zone_single_sensor_has_empty_entity_name(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "ZONE_NAMES", {"Zone_1": {"name": "Front door", "open": None}})

    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "open"
    )
    config = _serialize_deserialize(binary_sensor)
    # An empty name is sent explicitly. Leaving the key out would make Home
    # Assistant name the entity after the device class, which repeats the
    # device name in the friendly name.
    assert config["name"] == ""
    assert config["device"]["name"] == "Front door"
    assert config["default_entity_id"] == "binary_sensor.zone_1_open"


def test_zone_empty_entity_name_ignores_prefix(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "ZONE_NAMES", {"Zone_1": {"name": "Front door", "open": None}})
    monkeypatch.setattr(cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "Paradox ")

    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor(
        {"key": "Zone_1", "label": "Zone 1"}, "open"
    )
    assert _serialize_deserialize(binary_sensor)["name"] == ""


def test_system_sensor_name_from_config(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "SYSTEM_NAMES", {"power_battery": "baterijos įtampa"})

    sensor = mqtt_entity_factory.make_system_status("power", "battery")
    assert _serialize_deserialize(sensor)["name"] == "baterijos įtampa"


def test_pai_status_name_from_config(mqtt_entity_factory, monkeypatch):
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "SYSTEM_NAMES", {"pai_status": "PAI būsena"})

    sensor = mqtt_entity_factory.make_pai_status_sensor("paradox/interface/pai_status")
    assert _serialize_deserialize(sensor)["name"] == "PAI būsena"


def _serialize_deserialize(entity):
    return json.loads(json.dumps(entity, cls=SerializableToJSONEncoder))


def _make_device():
    detected_panel = DetectedPanel(1, "EVO", "6.10", "1234abcd")
    return Device(detected_panel)


def _get_expected_device_block():
    return {
        'identifiers': ['Paradox_1234abcd'],
        'manufacturer': 'Paradox',
        'model': 'EVO',
        'name': 'EVO',
        'sw_version': '6.10'
    }


def _get_expected_zone_device_block():
    return {
        'identifiers': ['Paradox_1234abcd_zone_Zone_1'],
        'manufacturer': 'Paradox',
        'model': 'Zone',
        'name': 'Zone 1',
        'via_device': 'Paradox_1234abcd'
    }


def test_device_model_is_sanitized_for_discovery_payload():
    device = Device(DetectedPanel(1, "MG505+\x00\xaa", "1.30 build 2", "1234abcd"))

    assert device.serialize() == {
        'manufacturer': 'Paradox',
        'model': 'MG505+',
        'identifiers': ['Paradox_1234abcd'],
        'name': 'MG505+',
        'sw_version': '1.30 build 2'
    }
