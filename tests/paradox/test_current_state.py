import asyncio
import binascii
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from paradox.hardware.evo.parsers import LiveEvent
from paradox.paradox import Paradox

from tests.hardware.evo.test_panel import create_evo192_panel


def send_initial_status(alarm):
    alarm._on_labels_load(
        data=dict(partition={1: dict(id=1, label="Partition 1", key="Partition_1")})
    )

    alarm._on_status_update(
        status=dict(
            partition={
                1: dict(
                    arm=False,
                    alarm_in_memory=False,
                    audible_alarm=False,
                    exit_delay=False,
                    was_in_alarm=False,
                )
            }
        )
    )

    alarm.storage.update_container_object.assert_any_call(
        "partition",
        "Partition_1",
        {"current_state": "disarmed", "target_state": "disarmed"},
    )


@pytest_asyncio.fixture(scope="function")
async def alarm(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_running_loop())
    # conn = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    # conn.connected = True
    alarm = Paradox(None)
    mocker.spy(alarm.storage, "update_container_object")
    alarm.panel = MagicMock()

    return alarm


@pytest.mark.asyncio
async def test_current_state_armed_away(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(partition={1: dict(arm=True)}))

    alarm.storage.update_container_object.assert_any_call(
        "partition",
        "Partition_1",
        {"current_state": "armed_away", "target_state": "armed_away"},
    )


@pytest.mark.asyncio
async def test_current_state_arming(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(partition={1: dict(arm=True, exit_delay=True)}))

    alarm.storage.update_container_object.assert_any_call(
        "partition",
        "Partition_1",
        {"current_state": "arming", "target_state": "armed_away"},
    )


@pytest.mark.asyncio
async def test_current_arm_stay(alarm):
    send_initial_status(alarm)

    alarm._on_status_update(status=dict(partition={1: dict(arm=True, arm_stay=True)}))

    alarm.storage.update_container_object.assert_any_call(
        "partition",
        "Partition_1",
        {"current_state": "armed_home", "target_state": "armed_home"},
    )


@pytest.mark.asyncio
async def test_current_alarm(mocker):
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_running_loop())
    alarm = Paradox(None)

    alarm.panel = create_evo192_panel(alarm)
    mocker.spy(alarm.storage, "update_container_object")

    send_initial_status(alarm)

    payload = binascii.unhexlify(
        "e2ff1cc414130b010f2c1801030000000000024f66666963652020202020202020202000d9"
    )
    raw = LiveEvent.parse(payload)
    alarm.handle_event_message(raw)

    await asyncio.sleep(0.01)

    alarm.storage.update_container_object.assert_any_call(
        "partition", "Partition_1", {"current_state": "triggered"}
    )
    alarm.panel = None


@pytest.mark.asyncio
async def test_unlabelled_partitions_do_not_break_state_updates(alarm):
    """Panel definitions cover every partition slot; labels only cover used ones.

    ``load_definitions`` merges an entry for *every* parsed slot, so the
    partition container legitimately holds objects that never received a
    ``key`` (``ElementTypeContainer`` guards every key access with
    ``if "key" in value`` for exactly this reason). ``_update_partition_states``
    used to index ``properties["key"]`` unconditionally, so a single unlabelled
    slot raised ``KeyError: 'key'`` and killed the ``events`` subscriber for
    every live event.
    """
    send_initial_status(alarm)

    # Partition 6 exists (definitions) but was never labelled.
    alarm.storage.get_container("partition").deep_merge(
        {6: dict(id=6, definition="disabled", arm=False)}
    )

    alarm._on_status_update(status=dict(partition={1: dict(arm=True)}))

    alarm.storage.update_container_object.assert_any_call(
        "partition",
        "Partition_1",
        {"current_state": "armed_away", "target_state": "armed_away"},
    )
