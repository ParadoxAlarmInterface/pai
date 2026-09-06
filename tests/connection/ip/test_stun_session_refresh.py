"""Renewing the TURN allocation must not block the event loop.

The refresh used to run inline in ``StunIPConnection.write()``, doing blocking
socket I/O on the event loop. Roughly every 500 s PAI stopped servicing the
panel, MQTT and every other interface until the TURN server answered -- and
with no socket timeout, a half-dead control socket stalled it indefinitely.
Everything then timed out at once, which looks exactly like a panel dropout.
"""

import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from paradox.connections.ip.connection import StunIPConnection
from paradox.connections.protocol_base import ConnectionProtocol
from paradox.exceptions import StunSessionRefreshFailed


def _connection(mocker):
    connection = StunIPConnection(
        site_id="home", email="em@em.em", panel_serial=None, password="test"
    )
    protocol = mocker.Mock(spec=ConnectionProtocol)
    protocol.is_active.return_value = True
    protocol.close = AsyncMock()
    connection._protocol = protocol
    connection.connected = True

    mocker.patch.object(connection.stun_session, "refresh_required", return_value=True)
    return connection


@pytest.mark.asyncio
async def test_a_due_refresh_runs_off_the_event_loop(mocker):
    connection = _connection(mocker)

    started = threading.Event()
    release = threading.Event()
    refresh_thread = {}

    def slow_refresh():
        refresh_thread["ident"] = threading.get_ident()
        started.set()
        release.wait(5)

    mocker.patch.object(connection.stun_session, "refresh_session", slow_refresh)

    connection.write(b"payload")

    # The write went out rather than waiting on the TURN server.
    connection._protocol.send_message.assert_called_once()

    # Let the refresh task start and hand its blocking call to a worker.
    await asyncio.sleep(0)
    assert started.wait(5)
    # The loop is still servicing coroutines while the refresh is blocked.
    await asyncio.wait_for(asyncio.sleep(0), 1)
    assert refresh_thread["ident"] != threading.get_ident()

    release.set()
    await asyncio.wait_for(connection._refresh_task, 5)
    assert connection.connected is True


@pytest.mark.asyncio
async def test_only_one_refresh_is_in_flight_at_a_time(mocker):
    connection = _connection(mocker)

    release = threading.Event()
    calls = []

    def slow_refresh():
        calls.append(1)
        release.wait(5)

    mocker.patch.object(connection.stun_session, "refresh_session", slow_refresh)

    connection.write(b"one")
    first_task = connection._refresh_task
    connection.write(b"two")

    assert connection._refresh_task is first_task

    release.set()
    await asyncio.wait_for(first_task, 5)
    assert calls == [1]


@pytest.mark.asyncio
async def test_a_failed_refresh_drops_the_connection(mocker):
    connection = _connection(mocker)
    mocker.patch.object(
        connection.stun_session,
        "refresh_session",
        side_effect=StunSessionRefreshFailed("allocation gone"),
    )

    connection.write(b"payload")
    await asyncio.wait_for(connection._refresh_task, 5)

    # The tunnel has stopped forwarding, so the main loop must reconnect
    # rather than keep writing into it.
    assert connection.connected is False
    assert connection._protocol is None
