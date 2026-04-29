"""
Command dispatch tests — Paradox.control_partition and control_utility_key.

Tests cover:
  - control_partition: resolves partition from storage, calls panel method,
    triggers status refresh.
  - control_utility_key: PRT3 guard, delegates to panel, error paths.
  - Logical success vs transport failure distinctions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradox.data.enums import RunState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paradox(monkeypatch, connection_type="PRT3"):
    """
    Build a Paradox instance with a mocked connection and panel.

    Returns (paradox, mock_panel).
    """
    from paradox.paradox import Paradox

    monkeypatch.setattr("paradox.paradox.cfg.CONNECTION_TYPE", connection_type)

    paradox = Paradox.__new__(Paradox)
    paradox.request_lock = asyncio.Lock()
    paradox.busy = asyncio.Lock()
    paradox.loop_wait_event = asyncio.Event()
    paradox._run_state = RunState.CONNECTED
    paradox.work_loop = None
    paradox._partition_arm_freeze_until = {}

    from paradox.data.memory_storage import MemoryStorage
    paradox.storage = MemoryStorage()

    mock_panel = MagicMock()
    mock_panel.control_partitions = AsyncMock(return_value=True)
    mock_panel.send_utility_key = AsyncMock(return_value=True)
    paradox.panel = mock_panel

    paradox._connection = MagicMock()
    paradox.request_status_refresh = MagicMock()

    return paradox, mock_panel


# ---------------------------------------------------------------------------
# control_partition — delegates to panel.control_partitions
# ---------------------------------------------------------------------------


async def test_control_partition_calls_panel(monkeypatch):
    """control_partition resolves partition from storage and calls panel."""
    from paradox.paradox import Paradox

    paradox, mock_panel = _make_paradox(monkeypatch)

    # Populate storage with a named partition
    paradox.storage.get_container("partition")[1] = {
        "id": 1, "key": 1, "label": "Home"
    }

    result = await paradox.control_partition("1", "arm")

    assert result is True
    mock_panel.control_partitions.assert_awaited_once()
    call_args = mock_panel.control_partitions.call_args
    assert call_args[0][1] == "arm"    # command arg
    paradox.request_status_refresh.assert_called_once()


async def test_control_partition_returns_false_if_not_found(monkeypatch):
    """control_partition returns False when no partition matches the selector."""
    paradox, mock_panel = _make_paradox(monkeypatch)
    # storage is empty

    result = await paradox.control_partition("99", "arm")

    assert result is False
    mock_panel.control_partitions.assert_not_awaited()


async def test_control_partition_panel_refuses(monkeypatch):
    """Panel returning False propagates as False to caller."""
    paradox, mock_panel = _make_paradox(monkeypatch)
    mock_panel.control_partitions = AsyncMock(return_value=False)

    paradox.storage.get_container("partition")[1] = {
        "id": 1, "key": 1, "label": "Home"
    }

    result = await paradox.control_partition("1", "disarm")

    assert result is False
    paradox.request_status_refresh.assert_called_once()


async def test_control_partition_not_implemented(monkeypatch):
    """NotImplementedError from panel is caught and returns False."""
    paradox, mock_panel = _make_paradox(monkeypatch)
    mock_panel.control_partitions = AsyncMock(side_effect=NotImplementedError)

    paradox.storage.get_container("partition")[1] = {
        "id": 1, "key": 1, "label": "Home"
    }

    result = await paradox.control_partition("1", "arm")
    assert result is False


# ---------------------------------------------------------------------------
# control_utility_key — PRT3 guard and delegation
# ---------------------------------------------------------------------------


async def test_control_utility_key_prt3_accepted(monkeypatch):
    """PRT3 path: delegates to panel.send_utility_key and returns True."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")

    result = await paradox.control_utility_key(5)

    assert result is True
    mock_panel.send_utility_key.assert_awaited_once_with(5)


async def test_control_utility_key_non_prt3_returns_false(monkeypatch):
    """Non-PRT3 connection type: returns False without calling panel."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="Serial")

    result = await paradox.control_utility_key(5)

    assert result is False
    mock_panel.send_utility_key.assert_not_awaited()


async def test_control_utility_key_panel_rejects(monkeypatch):
    """Panel returning False propagates as False."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(return_value=False)

    assert await paradox.control_utility_key(10) is False


async def test_control_utility_key_panel_not_implemented(monkeypatch):
    """NotImplementedError from panel is caught and returns False."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(side_effect=NotImplementedError)

    assert await paradox.control_utility_key(5) is False


async def test_control_utility_key_cancelled(monkeypatch):
    """CancelledError from panel is re-raised so the task can be cancelled cleanly."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(side_effect=asyncio.CancelledError)

    with pytest.raises(asyncio.CancelledError):
        await paradox.control_utility_key(5)


# ---------------------------------------------------------------------------
# Transport vs logical failure distinction
# ---------------------------------------------------------------------------


async def test_utility_key_transport_success_is_true(monkeypatch):
    """Panel &ok echo → True (transport and logical success)."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(return_value=True)

    assert await paradox.control_utility_key(1) is True


async def test_utility_key_transport_timeout_is_false(monkeypatch):
    """Timeout (panel never echoed) → False (transport failure)."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(return_value=False)  # panel returns False on timeout

    assert await paradox.control_utility_key(1) is False


async def test_utility_key_panel_rejection_is_false(monkeypatch):
    """Panel &fail echo → False (logical failure, transport succeeded)."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(return_value=False)

    assert await paradox.control_utility_key(2) is False


# ---------------------------------------------------------------------------
# handle_prt3_event_message — global partition event broadcast
# ---------------------------------------------------------------------------


def _make_paradox_with_partitions(monkeypatch):
    """Paradox instance pre-populated with two partitions in storage."""
    paradox, mock_panel = _make_paradox(monkeypatch)
    paradox.storage.get_container("partition")[1] = {
        "id": 1, "key": "home", "label": "Home", "arm": True, "exit_delay": True,
    }
    paradox.storage.get_container("partition")[2] = {
        "id": 2, "key": "downstairs", "label": "Downstairs", "arm": True, "exit_delay": True,
    }
    return paradox


async def test_global_disarm_event_clears_exit_delay_on_all_partitions(monkeypatch):
    """G014 with area=0 (global disarm) must clear exit_delay on every partition.

    Regression test for: disarming during exit delay from the panel keypad sends
    a global disarm event (area=0).  The previous code called
    get_container_object("partition", 0) which returned None and silently dropped
    the change, leaving exit_delay=True and HA stuck in 'arming' state.
    """
    from paradox.hardware.prt3.parser import PRT3SystemEvent

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"):
        paradox = _make_paradox_with_partitions(monkeypatch)

        # Simulate a global disarm event: area=0 means "all areas"
        msg = PRT3SystemEvent(group=14, number=1, area=0)
        paradox.handle_prt3_event_message(msg)

    p1 = paradox.storage.get_container_object("partition", 1)
    p2 = paradox.storage.get_container_object("partition", 2)
    assert p1["exit_delay"] is False, "partition 1 exit_delay must be cleared by global disarm"
    assert p2["exit_delay"] is False, "partition 2 exit_delay must be cleared by global disarm"
    assert p1["arm"] is False, "partition 1 arm must be cleared by global disarm"
    assert p2["arm"] is False, "partition 2 arm must be cleared by global disarm"


async def test_global_disarm_area255_clears_exit_delay_on_all_partitions(monkeypatch):
    """G014 with area=255 (any area) is also treated as global and clears all partitions."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"):
        paradox = _make_paradox_with_partitions(monkeypatch)

        msg = PRT3SystemEvent(group=14, number=1, area=255)
        paradox.handle_prt3_event_message(msg)

    p1 = paradox.storage.get_container_object("partition", 1)
    p2 = paradox.storage.get_container_object("partition", 2)
    assert p1["exit_delay"] is False
    assert p2["exit_delay"] is False


async def test_specific_area_disarm_only_updates_that_partition(monkeypatch):
    """G014 with a specific area (e.g. area=2) only updates partition 2, not partition 1."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"):
        paradox = _make_paradox_with_partitions(monkeypatch)

        msg = PRT3SystemEvent(group=14, number=1, area=2)
        paradox.handle_prt3_event_message(msg)

    p1 = paradox.storage.get_container_object("partition", 1)
    p2 = paradox.storage.get_container_object("partition", 2)
    assert p1["exit_delay"] is True,  "partition 1 must NOT be touched by area=2 event"
    assert p2["exit_delay"] is False, "partition 2 exit_delay must be cleared by area=2 disarm"


# ---------------------------------------------------------------------------
# Optimistic disarm — control_partition reflects panel &OK echo immediately
# ---------------------------------------------------------------------------


async def test_disarm_optimistically_clears_arm_and_exit_delay(monkeypatch):
    """control_partition('disarm') applies disarmed state on panel &OK echo.

    Without this the next RA poll lags 4–7 s on a busy panel and HA shows a
    transient 'armed' state because RA reports arm_state='armed_stay' for a
    moment after the disarm command (panel hasn't fully cleared its arm flags
    yet).  G-events alone aren't reliable: PRT3 ASCII-initiated disarms during
    exit delay don't always emit G014, only G065N000 (Ready) which per spec
    isn't an exit_delay-cleared signal.
    """
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    paradox.storage.get_container("partition")[2] = {
        "id": 2, "key": "downstairs", "label": "Downstairs",
        "arm": True, "arm_stay": True, "arm_away": False, "arm_force": False,
        "exit_delay": True, "entry_delay": False,
    }

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"), \
         patch("paradox.paradox.ps.sendMessage"), patch("paradox.paradox.ps.sendNotification"):
        result = await paradox.control_partition("2", "disarm")

    assert result is True
    p2 = paradox.storage.get_container_object("partition", 2)
    assert p2["arm"] is False
    assert p2["arm_stay"] is False
    assert p2["exit_delay"] is False
    assert p2["entry_delay"] is False


async def test_disarm_freezes_arm_against_stale_ra_poll(monkeypatch):
    """After a disarm, a stale RA poll showing armed_stay must NOT undo the optimistic disarm.

    The panel's internal state lags ~hundreds of ms after &OK; if RA polls run
    in that gap and report arm_state='armed_stay', they'd briefly re-assert
    arm=True and HA flashes 'armed_home' before the next poll corrects it.
    The freeze window drops arm-related keys from RA updates for a few seconds.
    """
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    paradox.storage.get_container("partition")[2] = {
        "id": 2, "key": "downstairs", "label": "Downstairs",
        "arm": True, "arm_stay": True, "exit_delay": True,
    }

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"), \
         patch("paradox.paradox.ps.sendMessage"), patch("paradox.paradox.ps.sendNotification"):
        await paradox.control_partition("2", "disarm")

        # Simulate an RA poll arriving during the freeze window — should be a no-op
        # for arm-related fields.  Other fields (trouble) flow through normally.
        stale_ra = {
            "partition": {
                2: {"arm": True, "arm_stay": True, "trouble": True},
            }
        }
        paradox._on_status_update(stale_ra)

    p2 = paradox.storage.get_container_object("partition", 2)
    assert p2["arm"] is False, "freeze must drop stale RA arm=True"
    assert p2["arm_stay"] is False, "freeze must drop stale RA arm_stay=True"
    assert p2["trouble"] is True, "non-arm RA fields must still flow through"


async def test_arm_does_not_optimistically_change_state(monkeypatch):
    """control_partition('arm_stay') leaves storage alone — G065N001 + RA set state."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    paradox.storage.get_container("partition")[2] = {
        "id": 2, "key": "downstairs", "label": "Downstairs",
        "arm": False, "arm_stay": False, "exit_delay": False,
    }

    with patch("paradox.paradox.ps.sendChange"), patch("paradox.paradox.ps.sendEvent"), \
         patch("paradox.paradox.ps.sendMessage"), patch("paradox.paradox.ps.sendNotification"):
        result = await paradox.control_partition("2", "arm_stay")

    assert result is True
    p2 = paradox.storage.get_container_object("partition", 2)
    assert p2["arm"] is False, "arm should be set by G065N001/RA, not optimistically"
    assert p2["exit_delay"] is False, "exit_delay should be set by G065N001, not optimistically"
