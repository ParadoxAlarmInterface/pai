"""
Runtime unit tests for paradox.hardware.prt3.panel.PRT3Panel.

Tests cover the request/reply cycle for each public method using a mocked
core+connection pair.  No real serial I/O occurs.

Mock wiring
-----------
``core.request_lock``  — real asyncio.Lock() (PRT3Panel acquires it in _prt3_send_wait)
``core.connection.write``  — MagicMock (records command bytes)
``core.connection.wait_for_message``  — AsyncMock (returns preconfigured messages)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradox.hardware.prt3.panel import PRT3Panel
from paradox.hardware.prt3.parser import (
    ARM_AWAY,
    ARM_DISARMED,
    ARM_STAY,
    PRT3AreaStatus,
    PRT3BufferFull,
    PRT3CommandEcho,
    PRT3CommStatus,
    PRT3LabelReply,
    PRT3ZoneStatus,
    ZONE_CLOSED,
    ZONE_OPEN,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def core():
    c = MagicMock()
    c.request_lock = asyncio.Lock()
    c.connection.write = MagicMock()
    c.connection.wait_for_message = AsyncMock(return_value=None)  # timeout by default
    return c


@pytest.fixture
def panel(core):
    return PRT3Panel(core)


# ---------------------------------------------------------------------------
# parse_message()
# ---------------------------------------------------------------------------


def test_parse_message_comm_ok(panel):
    result = panel.parse_message(b"COMM&ok\r")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is True


def test_parse_message_comm_fail(panel):
    result = panel.parse_message(b"COMM&fail\r")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is False


def test_parse_message_empty_returns_none(panel):
    assert panel.parse_message(b"") is None


def test_parse_message_non_ascii_returns_none(panel):
    assert panel.parse_message(b"\xff\xfe\r") is None


def test_parse_message_strips_cr(panel):
    """parse_message strips the trailing \\r before calling parse_line."""
    result = panel.parse_message(b"COMM&ok\r")
    assert isinstance(result, PRT3CommStatus)


# ---------------------------------------------------------------------------
# initialize_communication()
# ---------------------------------------------------------------------------


async def test_initialize_communication_ok(core, panel):
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommStatus(ok=True)
    )
    assert await panel.initialize_communication(None) is True


async def test_initialize_communication_fail(core, panel):
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommStatus(ok=False)
    )
    assert await panel.initialize_communication(None) is False


async def test_initialize_communication_timeout(core, panel):
    core.connection.wait_for_message = AsyncMock(
        side_effect=asyncio.TimeoutError
    )
    assert await panel.initialize_communication(None) is False


async def test_initialize_communication_ignores_password_arg(core, panel):
    """PRT3 has no password; argument must be accepted but ignored."""
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommStatus(ok=True)
    )
    assert await panel.initialize_communication("secret") is True


# ---------------------------------------------------------------------------
# load_definitions() — always returns {}
# ---------------------------------------------------------------------------


async def test_load_definitions_returns_empty(panel):
    result = await panel.load_definitions()
    assert result == {}


# ---------------------------------------------------------------------------
# request_status()
# ---------------------------------------------------------------------------


def _area_status(area: int, arm_state=ARM_DISARMED) -> PRT3AreaStatus:
    return PRT3AreaStatus(
        area=area,
        arm_state=arm_state,
        in_programming=False,
        trouble=False,
        not_ready=False,
        alarm=False,
        strobe=False,
        zone_in_memory=False,
    )


def _zone_status(zone: int, open_state=ZONE_CLOSED) -> PRT3ZoneStatus:
    return PRT3ZoneStatus(
        zone=zone,
        open_state=open_state,
        alarm=False,
        fire_alarm=False,
        supervision_trouble=False,
        low_battery=False,
    )


def _fail_echo(cmd: str) -> PRT3CommandEcho:
    return PRT3CommandEcho(cmd=cmd, ok=False)


async def test_request_status_returns_flat_dict(core, panel, monkeypatch):
    """One area + one zone returns expected flat status keys."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 1)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 1)

    area1 = _area_status(1, arm_state=ARM_AWAY)
    zone1 = _zone_status(1, open_state=ZONE_OPEN)

    core.connection.wait_for_message = AsyncMock(side_effect=[area1, zone1])

    result = await panel.request_status(0)

    assert "partition_arm" in result
    assert result["partition_arm"][1] is True
    assert "zone_open" in result
    assert result["zone_open"][1] is True


async def test_request_status_skips_fail_areas(core, panel, monkeypatch):
    """Areas returning &fail are silently excluded from the result."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 2)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 0)

    area1 = _area_status(1)
    fail2 = _fail_echo("RA002")

    core.connection.wait_for_message = AsyncMock(side_effect=[area1, fail2])

    result = await panel.request_status(0)
    # Area 1 present, area 2 absent
    assert 1 in result.get("partition_arm", {})
    assert 2 not in result.get("partition_arm", {})


async def test_request_status_timeout_gives_no_entry(core, panel, monkeypatch):
    """Timeouts (wait_for_message returns None) are logged but don't crash."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 1)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 0)

    core.connection.wait_for_message = AsyncMock(return_value=None)

    result = await panel.request_status(0)
    # No exception; result is empty or missing the timed-out area
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# control_partitions() — arm / quick-arm / disarm
# ---------------------------------------------------------------------------


async def test_control_partitions_quick_arm(core, panel, monkeypatch):
    """Quick-arm (no user code) sends AQ command and returns True on &ok."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "")

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AQ001", ok=True)
    )

    result = await panel.control_partitions([1], "arm")
    assert result is True
    call_args = core.connection.write.call_args[0][0]
    assert call_args.startswith(b"AQ001")


async def test_control_partitions_arm_with_code(core, panel, monkeypatch):
    """Arm with user code sends AA command."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "1234")

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AA001", ok=True)
    )

    result = await panel.control_partitions([1], "arm")
    assert result is True
    call_args = core.connection.write.call_args[0][0]
    assert call_args.startswith(b"AA001")


async def test_control_partitions_arm_stay(core, panel, monkeypatch):
    """arm_stay sends AQ with mode 'S'."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "")

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AQ001", ok=True)
    )

    result = await panel.control_partitions([1], "arm_stay")
    assert result is True
    cmd = core.connection.write.call_args[0][0]
    # Mode character 'S' at position 5 (AQ001S)
    assert cmd[5:6] == b"S"


async def test_control_partitions_disarm_no_code_returns_false(core, panel, monkeypatch):
    """Disarm without PRT3_USER_CODE configured must return False."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "")

    result = await panel.control_partitions([1], "disarm")
    assert result is False
    core.connection.write.assert_not_called()


async def test_control_partitions_disarm_with_code(core, panel, monkeypatch):
    """Disarm with user code sends AD command and returns True on &ok."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "1234")

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AD001", ok=True)
    )

    result = await panel.control_partitions([1], "disarm")
    assert result is True
    cmd = core.connection.write.call_args[0][0]
    assert cmd.startswith(b"AD001")


async def test_control_partitions_panel_rejects_command(core, panel, monkeypatch):
    """Panel returning &fail means the command was rejected → False."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "")

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AQ001", ok=False)
    )

    result = await panel.control_partitions([1], "arm")
    assert result is False


async def test_control_partitions_unknown_command(core, panel):
    result = await panel.control_partitions([1], "dance")
    assert result is False
    core.connection.write.assert_not_called()


async def test_control_partitions_multiple_accepted_if_any_ok(core, panel, monkeypatch):
    """Arming two partitions — first accepted, second rejected → True."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "")

    core.connection.wait_for_message = AsyncMock(
        side_effect=[
            PRT3CommandEcho(cmd="AQ001", ok=True),
            PRT3CommandEcho(cmd="AQ002", ok=False),
        ]
    )

    result = await panel.control_partitions([1, 2], "arm")
    assert result is True


# ---------------------------------------------------------------------------
# control_zones() / control_outputs() — not supported
# ---------------------------------------------------------------------------


async def test_control_zones_raises_not_implemented(panel):
    with pytest.raises(NotImplementedError):
        await panel.control_zones([1], "bypass")


async def test_control_outputs_raises_not_implemented(panel):
    with pytest.raises(NotImplementedError):
        await panel.control_outputs([1], "on")


# ---------------------------------------------------------------------------
# send_panic()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("panic_type,prefix", [
    ("emergency", b"PE"),
    ("medical",   b"PM"),
    ("fire",      b"PF"),
])
async def test_send_panic_accepted(core, panel, panic_type, prefix):
    echo_cmd = f"{prefix.decode('ascii')}001"
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd=echo_cmd, ok=True)
    )

    result = await panel.send_panic([1], panic_type, None)
    assert result is True
    cmd = core.connection.write.call_args[0][0]
    assert cmd.startswith(prefix)


async def test_send_panic_rejected_by_panel(core, panel):
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="PE001", ok=False)
    )
    assert await panel.send_panic([1], "emergency", None) is False


async def test_send_panic_timeout(core, panel):
    core.connection.wait_for_message = AsyncMock(return_value=None)
    assert await panel.send_panic([1], "fire", None) is False


async def test_send_panic_unknown_type(panel):
    assert await panel.send_panic([1], "unknown_panic_type", None) is False


# ---------------------------------------------------------------------------
# load_labels()
# ---------------------------------------------------------------------------


async def test_load_labels_returns_labels_dict(core, panel, monkeypatch):
    """Labels for area/zone/user are assembled into the expected nested dict."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 1)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 1)
    monkeypatch.setattr(cfg, "PRT3_MAX_USERS", 1)

    core.connection.wait_for_message = AsyncMock(
        side_effect=[
            PRT3LabelReply(element_type="area", index=1, label="Home      "),
            PRT3LabelReply(element_type="zone", index=1, label="Front Door"),
            PRT3LabelReply(element_type="user", index=1, label="Admin     "),
        ]
    )

    labels = await panel.load_labels()

    assert "partition" in labels
    assert labels["partition"][1]["label"] == "Home"
    assert "zone" in labels
    assert labels["zone"][1]["label"] == "Front Door"
    assert "user" in labels
    assert labels["user"][1]["label"] == "Admin"


async def test_load_labels_skips_fail_echo(core, panel, monkeypatch):
    """Areas/zones returning &fail are silently excluded."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 1)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 0)
    monkeypatch.setattr(cfg, "PRT3_MAX_USERS", 0)

    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AL001", ok=False)
    )

    labels = await panel.load_labels()
    assert labels.get("partition", {}) == {}


# ---------------------------------------------------------------------------
# _prt3_send_wait() — retry behaviour
# ---------------------------------------------------------------------------


async def test_send_wait_succeeds_on_first_attempt(core, panel):
    """No retry needed when the first attempt returns a reply."""
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommStatus(ok=True)
    )
    result = await panel._prt3_send_wait(b"COMM\r", lambda m: True, retries=2)
    assert result is not None
    assert core.connection.write.call_count == 1


async def test_send_wait_retries_on_timeout(core, panel):
    """A single timeout is retried; second attempt succeeds."""
    core.connection.wait_for_message = AsyncMock(
        side_effect=[asyncio.TimeoutError, PRT3CommStatus(ok=True)]
    )
    result = await panel._prt3_send_wait(b"COMM\r", lambda m: True, retries=2)
    assert result is not None
    assert core.connection.write.call_count == 2


async def test_send_wait_returns_none_when_all_retries_exhausted(core, panel):
    """Returns None only when every attempt times out."""
    core.connection.wait_for_message = AsyncMock(
        side_effect=asyncio.TimeoutError
    )
    result = await panel._prt3_send_wait(b"COMM\r", lambda m: True, retries=3)
    assert result is None
    assert core.connection.write.call_count == 3


async def test_send_wait_does_not_retry_on_fail_echo(core, panel):
    """A &fail echo is a definitive answer — no retry should occur."""
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="AQ001", ok=False)
    )
    result = await panel._prt3_send_wait(
        b"AQ001A\r",
        lambda m: isinstance(m, PRT3CommandEcho),
        retries=2,
    )
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is False
    assert core.connection.write.call_count == 1  # no second attempt


async def test_send_wait_buffer_full_returns_none(core, panel):
    """PRT3BufferFull on every attempt returns None without waiting full timeout."""
    core.connection.wait_for_message = AsyncMock(return_value=PRT3BufferFull())
    result = await panel._prt3_send_wait(
        b"AQ001A\r",
        lambda m: isinstance(m, PRT3CommandEcho),
        retries=1,
    )
    assert result is None
    assert core.connection.write.call_count == 1


async def test_send_wait_buffer_full_retries_then_succeeds(core, panel):
    """PRT3BufferFull on first attempt triggers a retry; second attempt succeeds."""
    ok_echo = PRT3CommandEcho(cmd="AQ001", ok=True)
    core.connection.wait_for_message = AsyncMock(
        side_effect=[PRT3BufferFull(), ok_echo]
    )
    result = await panel._prt3_send_wait(
        b"AQ001A\r",
        lambda m: isinstance(m, PRT3CommandEcho),
        retries=2,
    )
    assert result is ok_echo
    assert core.connection.write.call_count == 2


async def test_control_partitions_malformed_code_returns_false(core, panel, monkeypatch):
    """Malformed PRT3_USER_CODE returns False without propagating ValueError."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "PRT3_USER_CODE", "abc")

    result = await panel.control_partitions([1], "disarm")
    assert result is False
    core.connection.write.assert_not_called()


# ---------------------------------------------------------------------------
# send_utility_key()
# ---------------------------------------------------------------------------


async def test_send_utility_key_accepted(core, panel):
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="UK005", ok=True)
    )
    result = await panel.send_utility_key(5)
    assert result is True
    cmd = core.connection.write.call_args[0][0]
    assert cmd == b"UK005\r"


async def test_send_utility_key_rejected_by_panel(core, panel):
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="UK010", ok=False)
    )
    assert await panel.send_utility_key(10) is False


async def test_send_utility_key_timeout_returns_false(core, panel):
    core.connection.wait_for_message = AsyncMock(
        side_effect=asyncio.TimeoutError
    )
    assert await panel.send_utility_key(1) is False


async def test_send_utility_key_no_retry_on_timeout(core, panel):
    """Utility key must NOT retry on timeout — commands are not idempotent.

    A gate or latch toggles on each pulse; a retry would cause a double-trigger.
    On timeout the command returns False immediately without a second write.
    """
    core.connection.wait_for_message = AsyncMock(
        side_effect=[asyncio.TimeoutError, PRT3CommandEcho(cmd="UK001", ok=True)]
    )
    result = await panel.send_utility_key(1)
    assert result is False
    assert core.connection.write.call_count == 1


async def test_send_utility_key_invalid_number_raises(core, panel):
    """Out-of-range key raises ValueError from the encoder."""
    with pytest.raises(ValueError):
        await panel.send_utility_key(0)
    with pytest.raises(ValueError):
        await panel.send_utility_key(252)


async def test_send_utility_key_max_valid(core, panel):
    """Key 251 is the maximum valid value."""
    core.connection.wait_for_message = AsyncMock(
        return_value=PRT3CommandEcho(cmd="UK251", ok=True)
    )
    assert await panel.send_utility_key(251) is True
    cmd = core.connection.write.call_args[0][0]
    assert cmd == b"UK251\r"
