import asyncio

import pytest

from paradox.event import Change, EventLevel
from paradox.paradox import Paradox, ps


def test_partitions(mocker):
    alarm = Paradox()
    alarm.panel = mocker.MagicMock()
    alarm.panel.property_map = {
        "arm": dict(
            level=EventLevel.INFO,
            message={
                "True": "{Type} {label} is armed",
                "False": "{Type} {label} is disarmed",
            },
        ),
    }

    alarm._on_labels_load(
        data=dict(partition={1: dict(id=1, label="Partition 1", key="Partition_1")})
    )

    sendChange = mocker.patch("paradox.data.memory_storage.ps.sendChange")

    alarm.storage.update_container_object("partition", "Partition_1", dict(arm=True))

    sendChange.assert_called_once_with(
        Change("partition", "Partition_1", "arm", True, initial=True)
    )
    sendChange.reset_mock()

    assert isinstance(alarm.panel, mocker.MagicMock)

    alarm._on_status_update(status=dict(partition={1: dict(arm=False)}))

    assert isinstance(alarm.panel, mocker.MagicMock)

    sendChange.assert_any_call(
        Change("partition", "Partition_1", "current_state", "disarmed", initial=True)
    )
    sendChange.assert_any_call(
        Change("partition", "Partition_1", "target_state", "disarmed", initial=True)
    )
    sendChange.assert_any_call(
        Change("partition", "Partition_1", "arm", False, initial=False)
    )


def test_partitions_callable_prop(mocker):
    alarm = Paradox()
    alarm.panel = mocker.MagicMock()
    alarm.panel.property_map = {
        "arm": dict(
            level=EventLevel.INFO,
            message={
                "True": "{Type} {label} is armed",
                "False": "{Type} {label} is disarmed",
            },
        ),
    }

    alarm._on_labels_load(
        data=dict(partition={1: dict(id=1, label="Partition 1", key="Partition_1")})
    )

    sendChange = mocker.patch("paradox.data.memory_storage.ps.sendChange")

    alarm._on_status_update(status=dict(partition={1: dict(arm=False)}))

    sendChange.assert_any_call(
        Change("partition", "Partition_1", "arm", False, initial=True)
    )
    sendChange.reset_mock()

    alarm.storage.update_container_object(
        "partition", "Partition_1", dict(arm=lambda old: not old)
    )
    sendChange.assert_any_call(Change("partition", "Partition_1", "arm", True))
