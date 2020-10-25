import json

import pytest

from paradox.data.model import DetectedPanel
from paradox.interfaces.mqtt.entities.device import Device
from paradox.interfaces.mqtt.entities.factory import MQTTAutodiscoveryEntityFactory
from paradox.lib.utils import SerializableToJSONEncoder


@pytest.fixture
def mqtt_entity_factory():
    return MQTTAutodiscoveryEntityFactory("paradox/interface/availability", _make_device())

def test_alarm_control_panel_serialize(mqtt_entity_factory):
    alarm_control_panel = mqtt_entity_factory.make_alarm_control_panel_config({"key": "Partition_1", "label": "Partition 1"})
    assert _serialize_deserialize(alarm_control_panel) == {
        'unique_id': 'paradox_1234abcd_partition_partition_1',
        'name': 'Paradox 1234abcd Partition Partition 1',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/partitions/Partition_1/current_state',
        'command_topic': 'paradox/control/partitions/Partition_1',
        'device': _get_expected_device_block(),
        'payload_arm_away': 'arm',
        'payload_arm_home': 'arm_stay',
        'payload_arm_night': 'arm_sleep',
        'payload_disarm': 'disarm',
    }

    assert alarm_control_panel.get_configuration_topic() == "homeassistant/alarm_control_panel/1234abcd/partition_Partition_1/config"


def test_partition_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_partition_status_binary_sensor({"key": "Partition_1", "label": "Partition 1"}, "arm")
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_partition_partition_1_arm',
        'name': 'Paradox 1234abcd Partition Partition 1 Arm',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/partitions/Partition_1/arm',
        'device': _get_expected_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
    }

    assert binary_sensor.get_configuration_topic() == "homeassistant/binary_sensor/1234abcd/partition_Partition_1_arm/config"


def test_zone_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_zone_status_binary_sensor({"key": "Zone_1", "label": "Zone 1"}, "open")
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_zone_zone_1_open',
        'name': 'Paradox 1234abcd Zone Zone 1 Open',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/zones/Zone_1/open',
        'device': _get_expected_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
        'device_class': 'motion'
    }

    assert binary_sensor.get_configuration_topic() == "homeassistant/binary_sensor/1234abcd/zone_Zone_1_open/config"


def test_trouble_binary_sensor_serialize(mqtt_entity_factory):
    binary_sensor = mqtt_entity_factory.make_system_status("troubles", "ac_trouble")
    assert _serialize_deserialize(binary_sensor) == {
        'unique_id': 'paradox_1234abcd_system_troubles_ac_trouble',
        'name': 'Paradox 1234abcd System troubles Ac trouble',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/system/troubles/ac_trouble',
        'device': _get_expected_device_block(),
        'payload_on': 'True',
        'payload_off': 'False',
    }

    assert binary_sensor.get_configuration_topic() == "homeassistant/binary_sensor/1234abcd/system_troubles_ac_trouble/config"


def test_pai_status_sensor_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_pai_status_sensor("paradox/interface/pai_status")
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_pai_status',
        'name': 'Paradox 1234abcd PAI Status',
        'state_topic': 'paradox/interface/pai_status',
        'device': _get_expected_device_block()
    }

    assert sensor.get_configuration_topic() == "homeassistant/sensor/1234abcd/pai_status/config"


def test_run_system_status_sensor_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_system_status("power", "vdc")
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_system_power_vdc',
        'name': 'Paradox 1234abcd System Power Vdc',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/system/power/vdc',
        'device': _get_expected_device_block(),
        'unit_of_measurement': 'V'
    }

    assert sensor.get_configuration_topic() == "homeassistant/sensor/1234abcd/system_power_vdc/config"


def test_pgm_switch_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_pgm_switch({"key": "PGM_1", "label": "PGM 1"})
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_pgm_pgm_1_open',
        'name': 'Paradox 1234abcd PGM PGM 1 Open',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/outputs/PGM_1/on',
        'command_topic': 'paradox/control/outputs/PGM_1',
        'device': _get_expected_device_block(),
        'state_on': 'True',
        'state_off': 'False',
    }

    assert sensor.get_configuration_topic() == "homeassistant/switch/1234abcd/pgm_PGM_1_open/config"


def test_zone_bypass_switch_serialize(mqtt_entity_factory):
    sensor = mqtt_entity_factory.make_zone_bypass_switch({"key": "Zone_1", "label": "Zone 1"})
    assert _serialize_deserialize(sensor) == {
        'unique_id': 'paradox_1234abcd_zone_zone_1_bypass',
        'name': 'Paradox 1234abcd Zone Zone 1 Bypass',
        'availability_topic': 'paradox/interface/availability',
        'state_topic': 'paradox/states/zones/Zone_1/bypassed',
        'command_topic': 'paradox/control/zones/Zone_1',
        'device': _get_expected_device_block(),
        'state_on': 'True',
        'state_off': 'False',
        'payload_on': 'bypass',
        'payload_off': 'clear_bypass',
    }

    assert sensor.get_configuration_topic() == "homeassistant/switch/1234abcd/zone_Zone_1_bypass/config"


def _serialize_deserialize(entity):
    return json.loads(json.dumps(entity, cls=SerializableToJSONEncoder))


def _make_device():
    detected_panel = DetectedPanel(1, "EVO", "6.10", "1234abcd")
    return Device(detected_panel)


def _get_expected_device_block():
    return {
            'identifiers': ['Paradox', 'EVO', '1234abcd'],
            'manufacturer': 'Paradox',
            'model': 'EVO',
            'name': 'EVO',
            'sw_version': '6.10'
        }