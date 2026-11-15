import asyncio
from unittest.mock import AsyncMock

from construct import Container
import pytest

from paradox.connections.connection import Connection
from paradox.data.model import DetectedPanel
from paradox.exceptions import PanelNotDetected
from paradox.hardware import detect_panel
from paradox.hardware.binary import BinaryPanel
from paradox.hardware.panel import Panel
from paradox.hardware import registry
from paradox.paradox import Paradox


async def test_registered_protocol_connects_without_binary_assumptions(monkeypatch):
    calls = []

    class NewPanel(Panel):
        def parse_message(self, message, direction="topanel"):
            return None

        async def initialize_communication(self, password):
            assert alarm.panel is self
            calls.append("login")
            return True

    class NewConnection(Connection):
        panel_protocol = "new-protocol"

        async def connect(self):
            calls.append("open")
            return True

        def variable_message_length(self, mode):
            calls.append(("framing", mode))

    alarm = Paradox()
    alarm._connection = NewConnection()
    panel = NewPanel(alarm, variable_message_length=False)
    identity = DetectedPanel(None, "New panel", "1.0", "new-serial")

    async def discover(core):
        calls.append("discover")
        core.install_panel(panel)
        return panel, identity

    monkeypatch.setitem(registry.DISCOVERY, "new-protocol", (discover,))
    # Publishing is synchronous; record it without replacing the lifecycle.
    monkeypatch.setattr(
        "paradox.paradox.ps.sendMessage",
        lambda topic, **kwargs: (
            calls.append(topic) if topic == "panel_detected" else None
        ),
    )

    assert await alarm.connect()
    assert calls == ["open", "discover", ("framing", False), "login", "panel_detected"]


@pytest.mark.parametrize(
    "failure",
    [ConnectionError("refused"), asyncio.TimeoutError(), asyncio.CancelledError()],
)
async def test_strategy_failure_does_not_probe_another_protocol(monkeypatch, failure):
    core = Container(connection=Container(panel_protocol="test"))
    first = AsyncMock(side_effect=failure)
    fallback = AsyncMock()
    monkeypatch.setitem(registry.DISCOVERY, "test", (first, fallback))

    with pytest.raises(type(failure)):
        await detect_panel(core)
    fallback.assert_not_awaited()


async def test_only_unanswered_probe_advances_to_next_strategy(monkeypatch):
    core = Container(connection=Container(panel_protocol="test"))
    result = (object(), DetectedPanel(None, "Test", "1", "serial"))
    first = AsyncMock(return_value=None)
    fallback = AsyncMock(return_value=result)
    monkeypatch.setitem(registry.DISCOVERY, "test", (first, fallback))

    assert await detect_panel(core) is result
    first.assert_awaited_once_with(core)
    fallback.assert_awaited_once_with(core)


async def test_missing_discovery_fails_explicitly():
    core = Container(connection=Container(panel_protocol="unknown"))
    with pytest.raises(PanelNotDetected):
        await detect_panel(core)


async def test_exhausted_discovery_is_a_failed_connection(monkeypatch):
    from paradox.data.enums import RunState

    connection = Connection()
    connection.panel_protocol = "silent"
    connection.connect = AsyncMock(return_value=True)
    alarm = Paradox()
    alarm._connection = connection
    monkeypatch.setitem(registry.DISCOVERY, "silent", (AsyncMock(return_value=None),))

    assert await alarm.connect() is False
    assert alarm.run_state == RunState.ERROR


async def test_start_timeout_after_identification_never_falls_back(monkeypatch):
    core = Container(
        install_panel=lambda panel: None,
        connection=Container(
            panel_protocol="test",
            on_initiate_communication=AsyncMock(),
            start_communication_source_id=2,
        ),
        send_wait=AsyncMock(
            side_effect=[
                Container(
                    fields=Container(
                        value=Container(
                            label=b"Test",
                            application=Container(version=1, revision=0, build=0),
                            serial_number=bytes(4),
                        )
                    )
                ),
                asyncio.TimeoutError(),
            ]
        ),
    )
    fallback = AsyncMock()
    monkeypatch.setitem(registry.DISCOVERY, "test", (BinaryPanel.detect, fallback))

    with pytest.raises(asyncio.TimeoutError):
        await detect_panel(core)
    core.connection.on_initiate_communication.assert_awaited_once()
    fallback.assert_not_awaited()
