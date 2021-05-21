import asyncio
import datetime
import json

import pytest
from paho.mqtt.client import MQTTMessage

from paradox.event import Event
from paradox.interfaces.mqtt.basic import BasicMQTTInterface


def get_interface(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_event_loop())
    con = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    con.get_instance.return_value.connected = True
    con.get_instance.return_value.availability_topic = "paradox/interface/availability"
    con.get_instance.return_value.pai_status_topic = "paradox/interface/pai_status"
    interface = BasicMQTTInterface(mocker.MagicMock())
    interface.start()
    interface.on_connect(None, None, None, None)

    return interface


@pytest.mark.asyncio
async def test_handle_panel_event(mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        event = Event()
        event.label = "Test"
        event.minor = 0
        event.major = 0
        event.time = datetime.datetime(2019, 10, 18, 17, 15)

        interface._handle_panel_event(event)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_called_once_with(
            "paradox/events/raw",
            json.dumps(
                {
                    "additional_data": {},
                    "change": {},
                    "key": "None,Test,",
                    "label": "Test",
                    "level": "NOTSET",
                    "major": 0,
                    "message": "",
                    "minor": 0,
                    "tags": [],
                    "time": "2019-10-18T17:15:00",
                    "timestamp": 0,
                    "type": None,
                },
                sort_keys=True,
            ),
            0,
            True,
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.parametrize(
    "command,expected",
    [
        pytest.param(b"arm", "arm"),
        pytest.param(b"arm_stay", "arm_stay"),
        pytest.param(b"arm_sleep", "arm_sleep"),
        pytest.param(b"disarm", "disarm"),
        # with user
        pytest.param(b"arm USER", "arm"),
        pytest.param(b"arm_stay USER", "arm_stay"),
        pytest.param(b"arm_sleep USER", "arm_sleep"),
        pytest.param(b"disarm USER", "disarm"),
        # Homeassistant
        pytest.param(b"armed_home", "arm_stay"),
        pytest.param(b"armed_night", "arm_sleep"),
        pytest.param(b"armed_away", "arm"),
        pytest.param(b"disarmed", "disarm"),
    ],
)
@pytest.mark.asyncio
async def test_mqtt_handle_partition_control(command, expected, mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        message = MQTTMessage(topic=b"paradox/control/partition/First_floor")
        message.payload = command

        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)

        interface.alarm.control_partition.assert_called_once_with(
            "First_floor", expected
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_mqtt_handle_zone_control(mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        message = MQTTMessage(topic=b"paradox/control/zones/El_t_r")
        message.payload = b"clear_bypass"

        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)

        interface.alarm.control_zone.assert_called_once_with("El_t_r", "clear_bypass")
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_mqtt_handle_zone_control_utf8(mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        message = MQTTMessage(topic="paradox/control/zones/Előtér".encode("utf-8"))
        message.payload = b"clear_bypass"

        interface._mqtt_handle_zone_control(None, None, message)

        await asyncio.sleep(0.01)
        interface.alarm.control_zone.assert_called_once_with("Előtér", "clear_bypass")
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_mqtt_handle_send_panic(mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        partition = 1
        panic_type = "fire"  # 2
        userid = 3

        message = MQTTMessage(
            topic=f"paradox/panic/{panic_type}/{partition}".encode("utf-8")
        )
        message.payload = str(userid).encode("utf-8")

        interface._mqtt_handle_send_panic(None, None, message)

        await asyncio.sleep(0.01)
        interface.alarm.send_panic.assert_called_once_with("1", "fire", "3")
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_mqtt_handle_door_control(mocker):
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)

        message = MQTTMessage(topic="paradox/control/doors/Door 1".encode("utf-8"))
        message.payload = b"unlock"

        interface._mqtt_handle_door_control(None, None, message)

        await asyncio.sleep(0.01)
        interface.alarm.control_door.assert_called_once_with("Door 1", "unlock")
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()
