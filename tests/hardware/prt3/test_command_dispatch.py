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
    """CancelledError from panel is caught and returns False."""
    paradox, mock_panel = _make_paradox(monkeypatch, connection_type="PRT3")
    mock_panel.send_utility_key = AsyncMock(side_effect=asyncio.CancelledError)

    assert await paradox.control_utility_key(5) is False


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
