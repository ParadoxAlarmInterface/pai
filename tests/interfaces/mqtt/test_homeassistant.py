import pytest

from pytest_mock import mocker

from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface
from paradox.lib.ps import sendMessage


def send_initial_status():
    sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partiton 1',
                key='Partiton_1'
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


@pytest.mark.asyncio
async def test_hass_armed_away(mocker):
    interface = HomeAssistantMQTTInterface()
    mocker.patch.object(interface, "mqtt")
    interface.start()

    await interface._started.wait()
    send_initial_status()

    assert interface.partitions[1]['status'] == 'disarmed'

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True
            )
        }
    ))

    assert interface.partitions[1]['status'] == 'armed_away'

    interface.stop()

@pytest.mark.asyncio
async def test_hass_pending(mocker):
    interface = HomeAssistantMQTTInterface()
    mocker.patch.object(interface, "mqtt")
    interface.start()

    await interface._started.wait()
    send_initial_status()

    assert interface.partitions[1]['status'] == 'disarmed'

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True,
                exit_delay=True
            )
        }
    ))

    assert interface.partitions[1]['status'] == 'pending'

    interface.stop()

@pytest.mark.asyncio
async def test_hass_arm_stay(mocker):
    interface = HomeAssistantMQTTInterface()
    mocker.patch.object(interface, "mqtt")
    interface.start()

    await interface._started.wait()
    send_initial_status()

    assert interface.partitions[1]['status'] == 'disarmed'

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True,
                arm_stay=True
            )
        }
    ))

    assert interface.partitions[1]['status'] == 'armed_home'

    interface.stop()

@pytest.mark.asyncio
async def test_hass_arm_stay(mocker):
    interface = HomeAssistantMQTTInterface()
    mocker.patch.object(interface, "mqtt")
    interface.start()

    await interface._started.wait()
    send_initial_status()

    assert interface.partitions[1]['status'] == 'disarmed'

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True,
                arm_stay=True
            )
        }
    ))

    assert interface.partitions[1]['status'] == 'armed_home'

    interface.stop()

@pytest.mark.asyncio
async def test_hass_alarm(mocker):
    interface = HomeAssistantMQTTInterface()
    mocker.patch.object(interface, "mqtt")
    interface.start()

    await interface._started.wait()
    send_initial_status()

    assert interface.partitions[1]['status'] == 'disarmed'

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                audible_alarm=True
            )
        }
    ))

    assert interface.partitions[1]['status'] == 'triggered'

    interface.stop()