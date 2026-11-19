import asyncio
import datetime
import json

from paho.mqtt.client import MQTTMessage
import pytest

from paradox.event import Event
from paradox.interfaces.mqtt.basic import BasicMQTTInterface


def get_interface(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_running_loop())
    con = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    con.get_instance.return_value.connected = True
    con.get_instance.return_value.availability_topic = "paradox/interface/availability"
    con.get_instance.return_value.pai_status_topic = "paradox/interface/run_status"
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

        message = MQTTMessage(topic=b"paradox/control/partitions/First_floor")
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

        message = MQTTMessage(topic="paradox/control/zones/Előtér".encode())
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

        message = MQTTMessage(topic=f"paradox/panic/{panic_type}/{partition}".encode())
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

        message = MQTTMessage(topic=b"paradox/control/doors/Door 1")
        message.payload = b"unlock"

        interface._mqtt_handle_door_control(None, None, message)

        await asyncio.sleep(0.01)
        interface.alarm.control_door.assert_called_once_with("Door 1", "unlock")
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_definitions_loaded_again_are_published_again(mocker):
    mocker.patch("paradox.interfaces.mqtt.basic.cfg.MQTT_PUBLISH_DEFINITIONS", True)
    interface = get_interface(mocker)
    try:
        await asyncio.sleep(0.01)
        interface._handle_panel_definitions(
            {"zone": {14: {"definition": "instant_full"}}}
        )
        interface._handle_panel_labels({"zone": {14: {"key": "IR_S_SOL"}}})
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            "paradox/definitions/zones/IR_S_SOL/definition", "instant_full", 0, True
        )

        interface.mqtt.publish.reset_mock()
        interface._handle_panel_definitions({"zone": {14: {"definition": "instant"}}})
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            "paradox/definitions/zones/IR_S_SOL/definition", "instant", 0, True
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_reloaded_labels_publish_definitions_for_renamed_and_new_zones(mocker):
    mocker.patch("paradox.interfaces.mqtt.basic.cfg.MQTT_PUBLISH_DEFINITIONS", True)
    interface = get_interface(mocker)
    try:
        interface._handle_panel_definitions({"zone": {14: {"definition": "instant"}}})
        interface._handle_panel_labels({"zone": {14: {"key": "Old_name"}}})
        await asyncio.sleep(0.01)
        interface.mqtt.publish.reset_mock()

        interface._handle_panel_definitions(
            {
                "zone": {
                    14: {"definition": "instant"},
                    15: {"definition": "delay_1"},
                }
            }
        )
        interface._handle_panel_labels(
            {"zone": {14: {"key": "New_name"}, 15: {"key": "New_zone"}}}
        )
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(asyncio.sleep(0), interface.loop)
        )

        interface.mqtt.publish.assert_any_call(
            "paradox/definitions/zones/New_name/definition", "instant", 0, True
        )
        interface.mqtt.publish.assert_any_call(
            "paradox/definitions/zones/New_zone/definition", "delay_1", 0, True
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_zone_control_routed_through_paho_subscription(mocker, caplog):
    from paho.mqtt.client import CallbackAPIVersion, Client

    client = Client(CallbackAPIVersion.VERSION2)
    interface = get_interface(mocker)
    try:
        interface.alarm.control_zone = mocker.AsyncMock(return_value=True)
        interface.mqtt.message_callback_add.side_effect = client.message_callback_add
        interface.on_connect(None, None, None, None)

        message = MQTTMessage(topic=b"paradox/control/zones/Zone_07")
        message.payload = b"bypass"
        with caplog.at_level("INFO", logger="PAI"):
            client._handle_on_message(message)
            await asyncio.sleep(0.01)

        interface.alarm.control_zone.assert_called_once_with("Zone_07", "bypass")
        assert "Zone command: Zone_07=bypass user: None" in caplog.text
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()
