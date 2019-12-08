import datetime
import json

import pytest
from paho.mqtt.client import MQTTMessage

from paradox.event import Event
from paradox.interfaces.mqtt.basic import BasicMQTTInterface


@pytest.mark.asyncio
async def test_handle_panel_event(mocker):
    interface = BasicMQTTInterface()
    interface.mqtt = mocker.MagicMock()

    event = Event()
    event.label = "Test"
    event.minor = 0
    event.major = 0
    event.time = datetime.datetime(2019, 10, 18, 17, 15)

    interface._handle_panel_event(event)
    interface.mqtt.publish.assert_called_once_with('paradox/events/raw',
                                                   json.dumps({"additional_data": {}, "change": {},
                                                               "key": "None,Test,", "label": "Test",
                                                               "level": "NOTSET", "major": 0, "message": "",
                                                               "minor": 0, "tags": [],
                                                               "time": "2019-10-18T17:15:00", "timestamp": 0,
                                                               "type": None}, sort_keys=True),
                                                   0, True)

@pytest.mark.parametrize("command,expected", [
    pytest.param(b'arm', 'arm'),
    pytest.param(b'arm_stay', 'arm_stay'),
    pytest.param(b'arm_sleep', 'arm_sleep'),
    pytest.param(b'disarm', 'disarm'),

    # Homeassistant
    pytest.param(b'armed_home', 'arm_stay'),
    pytest.param(b'armed_night', 'arm_sleep'),
    pytest.param(b'armed_away', 'arm'),
    pytest.param(b'disarmed', 'disarm')
])
def test_mqtt_handle_partition_control(command, expected, mocker):
    interface = BasicMQTTInterface()
    interface.alarm = mocker.MagicMock()

    message = MQTTMessage(topic=b'paradox/control/partition/First_floor')
    message.payload = command

    interface._mqtt_handle_partition_control(None, None, message)

    interface.alarm.control_partition.assert_called_once_with(
        "First_floor",
        expected
    )

def test_mqtt_handle_zone_control(mocker):
    interface = BasicMQTTInterface()
    interface.alarm = mocker.MagicMock()

    message = MQTTMessage(topic=b'paradox/control/zones/El_t_r')
    message.payload = b'clear_bypass'

    interface._mqtt_handle_zone_control(None, None, message)

    interface.alarm.control_zone.assert_called_once_with(
        "El_t_r",
        "clear_bypass"
    )

def test_mqtt_handle_zone_control_utf8(mocker):
    interface = BasicMQTTInterface()
    interface.alarm = mocker.MagicMock()

    message = MQTTMessage(topic='paradox/control/zones/Előtér'.encode('utf-8'))
    message.payload = b'clear_bypass'

    interface._mqtt_handle_zone_control(None, None, message)

    interface.alarm.control_zone.assert_called_once_with(
        "Előtér",
        "clear_bypass"
    )