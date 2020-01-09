import pytest
import asyncio
from mock import MagicMock

from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface
from paradox.lib.ps import sendMessage
import json


@pytest.mark.asyncio
async def test_hass():
    interface = HomeAssistantMQTTInterface()
    interface.mqtt = MagicMock()
    interface.start()

    try:
        await asyncio.sleep(0.1)  # TODO: Bad way to wait for a start

        sendMessage("labels_loaded", data=dict(
            partition={
                1: dict(
                    id=1,
                    label='Partition 1',
                    key='Partition_1'
                )
            }
        ))

        sendMessage("status_update", status=dict(
            partition={
                1: dict(
                    arm=False
                )
            }
        ))

        interface.mqtt.publish.assert_called_with(
            'homeassistant/alarm_control_panel/pai/Partition_1/config',
            json.dumps(
                dict(
                    name='Partition 1',
                    unique_id="pai_partition_Partition_1",
                    command_topic='paradox/control/partitions/Partition_1',
                    state_topic='paradox/states/partitions/Partition_1/current_state',
                    availability_topic='paradox/interface/MQTTInterface',
                    device=dict(),
                    payload_disarm="disarm",
                    payload_arm_home="arm_stay",
                    payload_arm_away="arm",
                    payload_arm_night="arm_sleep"
                )
            ), 0, True)
    finally:
        interface.stop()
