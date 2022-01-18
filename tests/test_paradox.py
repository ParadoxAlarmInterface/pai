from unittest.mock import AsyncMock

import pytest

from paradox.hardware import Panel
from paradox.paradox import Paradox


@pytest.mark.asyncio
async def test_send_panic(mocker):
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.send_panic = AsyncMock()

    alarm.storage.get_container("partition").deep_merge(
        {1: {"id": 1, "key": "Partition 1"}}
    )
    alarm.storage.get_container("user").deep_merge({3: {"id": 3, "key": "User 3"}})

    assert await alarm.send_panic("1", "fire", "3")
    alarm.panel.send_panic.assert_called_once_with([1], "fire", 3)
    alarm.panel.send_panic.reset_mock()

    assert await alarm.send_panic("Partition 1", "fire", "User 3")
    alarm.panel.send_panic.assert_called_once_with([1], "fire", 3)


@pytest.mark.asyncio
async def test_control_doors(mocker):
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.control_doors = AsyncMock()

    alarm.storage.get_container("door").deep_merge({1: {"id": 1, "key": "Door 1"}})

    assert await alarm.control_door("1", "unlock")
    alarm.panel.control_doors.assert_called_once_with([1], "unlock")
    alarm.panel.control_doors.reset_mock()

    assert await alarm.control_door("Door 1", "unlock")
    alarm.panel.control_doors.assert_called_once_with([1], "unlock")
