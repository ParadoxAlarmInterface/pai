import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from construct import Container
import pytest

from paradox.data.memory_storage import MemoryStorage
from paradox.hardware.spectra_magellan import parsers
from paradox.hardware.spectra_magellan.panel import Panel


@pytest.fixture
def panel():
    core = SimpleNamespace(
        storage=MemoryStorage(), send_wait=AsyncMock(return_value=Container())
    )
    response = Container(
        fields=Container(value=Container(firmware=Container(version=5)))
    )
    return Panel(core, response)


@pytest.mark.parametrize(
    "command,bypassed,should_toggle",
    [
        ("bypass", False, True),
        ("bypass", True, False),
        ("clear_bypass", True, True),
        ("clear_bypass", False, False),
    ],
)
async def test_zone_bypass_uses_cached_state(panel, command, bypassed, should_toggle):
    zones = panel.core.storage.get_container("zone")
    zones[7] = {"key": "Zone_07", "bypassed": bypassed}

    assert await panel.control_zones([7], command) is True

    if should_toggle:
        panel.core.send_wait.assert_awaited_once_with(
            parsers.PerformAction,
            {"action": 0x10, "argument": 6},
            reply_expected=0x4,
            retries=1,
        )
    else:
        panel.core.send_wait.assert_not_awaited()
    assert zones[7]["bypassed"] is bypassed


@pytest.mark.parametrize("command", ["bypass", "clear_bypass"])
@pytest.mark.parametrize("state", [None, {}, {"bypassed": None}, {"bypassed": "False"}])
async def test_zone_bypass_unknown_state_is_refused(panel, caplog, command, state):
    if state is not None:
        panel.core.storage.get_container("zone")[7] = state

    assert await panel.control_zones([7], command) is False

    panel.core.send_wait.assert_not_awaited()
    assert "zone 7: bypass state is unknown" in caplog.text


async def test_zone_bypass_multiple_zones(panel):
    zones = panel.core.storage.get_container("zone")
    zones[1] = {"bypassed": True}
    zones[2] = {"bypassed": False}
    zones[3] = {}

    assert await panel.control_zones([1, 2, 3], "bypass") is True

    panel.core.send_wait.assert_awaited_once_with(
        parsers.PerformAction,
        {"action": 0x10, "argument": 1},
        reply_expected=0x4,
        retries=1,
    )


async def test_zone_bypass_no_reply_is_not_accepted(panel):
    panel.core.storage.get_container("zone")[7] = {"bypassed": False}
    panel.core.send_wait.return_value = None

    assert await panel.control_zones([7], "bypass") is False


async def test_zone_bypass_timeout_does_not_change_cached_state(panel):
    zones = panel.core.storage.get_container("zone")
    zones[7] = {"bypassed": False}
    panel.core.send_wait.side_effect = asyncio.TimeoutError

    with pytest.raises(asyncio.TimeoutError):
        await panel.control_zones([7], "bypass")

    panel.core.send_wait.assert_awaited_once_with(
        parsers.PerformAction,
        {"action": 0x10, "argument": 6},
        reply_expected=0x4,
        retries=1,
    )
    assert zones[7]["bypassed"] is False


async def test_zone_bypass_invalid_command_is_refused(panel):
    panel.core.storage.get_container("zone")[7] = {"bypassed": False}

    assert await panel.control_zones([7], "invalid") is False

    panel.core.send_wait.assert_not_awaited()


async def test_zone_bypass_empty_selection_is_refused(panel):
    assert await panel.control_zones([], "bypass") is False

    panel.core.send_wait.assert_not_awaited()
