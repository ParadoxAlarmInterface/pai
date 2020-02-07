import asyncio
import binascii

import pytest
from mock import MagicMock

from paradox.hardware.evo import Panel_EVO192
from paradox.hardware.evo.parsers import LiveEvent
from paradox.paradox import Paradox


def send_initial_status(alarm):
    alarm._on_labels_load(data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            )
        }
    ))

    alarm._on_status_update(status=dict(
        partition={
            1: dict(
                arm=False,
                alarm_in_memory=False,
                audible_alarm=False,
                exit_delay=False,
                was_in_alarm=False
            )
        }
    ))

    alarm.storage.update_container_object.assert_any_call('partition', 'Partition_1', {
        'current_state': 'disarmed',
        'target_state': 'disarmed'
    })


@pytest.fixture(scope="function")
def alarm(mocker):
    mocker.patch('paradox.lib.utils.main_thread_loop', asyncio.get_event_loop())
    # conn = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    # conn.connected = True
    alarm = Paradox(None)
    mocker.spy(alarm.storage, 'update_container_object')
    alarm.panel = MagicMock()

    return alarm


@pytest.mark.asyncio
async def test_current_state_armed_away(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(
        partition={
            1: dict(
                arm=True
            )
        }
    ))

    alarm.storage.update_container_object.assert_any_call('partition', 'Partition_1', {
        'current_state': 'armed_away',
        'target_state': 'armed_away'
    })


@pytest.mark.asyncio
async def test_current_state_pending(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(
        partition={
            1: dict(
                arm=True,
                exit_delay=True
            )
        }
    ))

    alarm.storage.update_container_object.assert_any_call('partition', 'Partition_1', {
        'current_state': 'pending',
        'target_state': 'armed_away'
    })


@pytest.mark.asyncio
async def test_current_arm_stay(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(
        partition={
            1: dict(
                arm=True,
                arm_stay=True
            )
        }
    ))

    alarm.storage.update_container_object.assert_any_call('partition', 'Partition_1', {
        'current_state': 'armed_home',
        'target_state': 'armed_home'
    })


@pytest.mark.asyncio
async def test_current_alarm(mocker):
    mocker.patch('paradox.lib.utils.main_thread_loop', asyncio.get_event_loop())
    alarm = Paradox(None)
    alarm.panel = Panel_EVO192(alarm, 5)
    mocker.spy(alarm.storage, 'update_container_object')

    send_initial_status(alarm)

    payload = binascii.unhexlify('e2ff1cc414130b010f2c1801030000000000024f66666963652020202020202020202000d9')
    raw = LiveEvent.parse(payload)
    alarm.handle_event_message(raw)

    await asyncio.sleep(0.01)

    alarm.storage.update_container_object.assert_any_call('partition', 'Partition_1', {
        'current_state': 'triggered'
    })
    alarm.panel = None
