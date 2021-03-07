import asyncio
import json
from json.decoder import JSONDecodeError

import pytest

from paradox.config import config as cfg
from paradox.data.model import DetectedPanel
from paradox.hardware.common import ProductIdEnum
from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface
from paradox.lib.ps import sendMessage
from tests.hardware.evo.test_panel import create_evo192_panel


@pytest.mark.asyncio
async def test_hass(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_event_loop())
    mocker.patch.multiple(cfg, MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE=True)
    con = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    con.get_instance.return_value.availability_topic = "paradox/interface/availability"
    con.get_instance.return_value.pai_status_topic = "paradox/interface/pai_status"

    alarm = mocker.MagicMock()

    alarm.panel = create_evo192_panel(alarm)
    interface = HomeAssistantMQTTInterface(alarm)
    interface.start()
    interface.on_connect(None, None, None, None)
    assert (
        interface.connected_future.done()
        and interface.connected_future.result() is True
    )

    try:
        await asyncio.sleep(0.01)  # TODO: Bad way to wait for a start

        sendMessage(
            "panel_detected",
            panel=DetectedPanel(
                ProductIdEnum.parse(b"\x05"), "EVO192", "6.80 build 5", "aabbccdd"
            ),
        )

        sendMessage(
            "labels_loaded",
            data=dict(
                partition={1: dict(id=1, label="Partition 1", key="Partition_1")}
            ),
        )

        sendMessage("status_update", status=dict(partition={1: dict(arm=False)}))

        await asyncio.sleep(0.01)

        assert_any_call_with_json(interface.mqtt.publish,
            "homeassistant/sensor/aabbccdd/pai_status/config",
            {
                "name": "Paradox aabbccdd PAI Status",
                "unique_id": "paradox_aabbccdd_pai_status",
                "state_topic": "paradox/interface/pai_status",
                "device": {
                    "manufacturer": "Paradox",
                    "model": "EVO192",
                    "identifiers": ["Paradox_EVO192_aabbccdd"],
                    "name": "EVO192",
                    "sw_version": "6.80 build 5",
                },
            },
            0,
            True
        )

        assert_any_call_with_json(interface.mqtt.publish,
            "homeassistant/alarm_control_panel/aabbccdd/partition_partition_1/config",
            {
                "name": "Paradox aabbccdd Partition Partition 1",
                "unique_id": "paradox_aabbccdd_partition_partition_1",
                "command_topic": "paradox/control/partitions/Partition_1",
                "state_topic": "paradox/states/partitions/Partition_1/current_state",
                "availability_topic": "paradox/interface/availability",
                "device": {
                    "manufacturer": "Paradox",
                    "model": "EVO192",
                    "identifiers": ["Paradox_EVO192_aabbccdd"],
                    "name": "EVO192",
                    "sw_version": "6.80 build 5",
                },
                "payload_disarm": "disarm",
                "payload_arm_home": "arm_stay",
                "payload_arm_away": "arm",
                "payload_arm_night": "arm_sleep"
            },
            0,
            True
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


def _decode_json(value):
    if isinstance(value, str) and value.startswith(('{', '[')):
        try:
            return json.loads(value)
        except JSONDecodeError:
            pass

    return value


def _decode_arguments(*args, **kwargs):
    new_arg = tuple(_decode_json(arg) for arg in args)
    new_kwarg = dict((key, _decode_json(val)) for key, val in kwargs)
    return new_arg, new_kwarg


def assert_any_call_with_json(self, *args, **kwargs):
    actual = [_decode_arguments(*args, **kwargs) for args, kwargs in self.call_args_list]
    expected = (args, kwargs)

    assert expected in actual
