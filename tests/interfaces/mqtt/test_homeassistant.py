import asyncio
import json

import pytest
from paradox.data.model import DetectedPanel
from paradox.hardware.common import ProductIdEnum
from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface
from paradox.lib.ps import sendMessage
from tests.hardware.evo.test_panel import create_evo192_panel


@pytest.mark.asyncio
async def test_hass(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_event_loop())
    con = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    con.get_instance.return_value.availability_topic = "paradox/interface/availability"
    con.get_instance.return_value.run_status_topic = "paradox/interface/run_status"

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

        interface.mqtt.publish.assert_any_call(
            "homeassistant/sensor/aabbccdd/run_status/config",
            json.dumps(
                {
                    "name": "Run status",
                    "unique_id": "aabbccdd_partition_run_status",
                    "state_topic": "paradox/interface/run_status",
                    "device": {
                        "manufacturer": "Paradox",
                        "model": "EVO192",
                        "identifiers": ["Paradox", "EVO192", "aabbccdd"],
                        "name": "EVO192",
                        "sw_version": "6.80 build 5",
                    },
                }
            ),
            0,
            True,
        )

        interface.mqtt.publish.assert_any_call(
            "homeassistant/alarm_control_panel/aabbccdd/Partition_1/config",
            json.dumps(
                {
                    "name": "Partition 1",
                    "unique_id": "aabbccdd_partition_Partition_1",
                    "command_topic": "paradox/control/partitions/Partition_1",
                    "state_topic": "paradox/states/partitions/Partition_1/current_state",
                    "availability_topic": "paradox/interface/availability",
                    "device": {
                        "manufacturer": "Paradox",
                        "model": "EVO192",
                        "identifiers": ["Paradox", "EVO192", "aabbccdd"],
                        "name": "EVO192",
                        "sw_version": "6.80 build 5",
                    },
                    "payload_disarm": "disarm",
                    "payload_arm_home": "arm_stay",
                    "payload_arm_away": "arm",
                    "payload_arm_night": "arm_sleep",
                }
            ),
            0,
            True,
        )
    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()
