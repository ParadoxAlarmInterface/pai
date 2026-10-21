import logging
from unittest.mock import MagicMock, patch

import pytest

from paradox import main as pai_main


class FakeAlarm:
    """Drives _run() through a scripted sequence of connect outcomes."""

    def __init__(self, script):
        self._script = list(script)
        self.attempts = 0

    async def full_connect(self):
        self.attempts += 1
        return self._script[self.attempts - 1] != "fail"

    async def loop(self):
        if self._script[self.attempts - 1] == "stop":
            raise KeyboardInterrupt

    async def disconnect(self):
        pass


async def _nosleep(*args, **kwargs):
    return None


async def run_scripted(script, caplog):
    alarm = FakeAlarm(script)
    interface_manager = MagicMock()
    interface_manager.interfaces = []

    clock = [1000.0]

    def monotonic():
        clock[0] += 100
        return clock[0]

    with patch.object(
        pai_main, "InterfaceManager", return_value=interface_manager
    ), patch.object(pai_main.asyncio, "sleep", new=_nosleep), patch.object(
        pai_main.time, "monotonic", monotonic
    ):
        with caplog.at_level(logging.DEBUG, logger="PAI"):
            await pai_main._run(alarm)

    return [r.message for r in caplog.records]


@pytest.mark.parametrize("failures", [1, 3])
async def test_cold_start_failures_do_not_log_a_recovery(failures, caplog):
    """A first-ever connect must never claim to have "recovered"."""
    messages = await run_scripted(["fail"] * failures + ["stop"], caplog)

    assert [m for m in messages if "Unable to connect to alarm" in m]
    assert not [m for m in messages if "Connection recovered" in m]


async def test_recovery_is_logged_after_a_real_session_drops(caplog):
    messages = await run_scripted(["ok", "fail", "stop"], caplog)

    assert [m for m in messages if "Panel connection ended after" in m]
    assert [m for m in messages if "Connection recovered after" in m]


async def test_first_successful_connect_logs_no_recovery(caplog):
    messages = await run_scripted(["stop"], caplog)

    assert not [m for m in messages if "Connection recovered" in m]


async def test_banner_reports_version_and_connection(caplog):
    messages = await run_scripted(["stop"], caplog)

    assert any("PAI " in m for m in messages)
    assert any("Connection:" in m for m in messages)
