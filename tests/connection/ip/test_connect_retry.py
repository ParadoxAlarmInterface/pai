"""A failed IP connect attempt must not leave its socket behind.

``_try_connect`` stores the protocol as soon as the socket opens and only then
runs the module handshake. A handshake failure used to leave that socket open
and unowned: the next attempt overwrote ``_protocol``, and
``ConnectionProtocol`` deliberately does not close the transport in
``__del__``. The IP module serves one session at a time, so PAI spent its three
retries competing with its own orphans -- and it took them back to back, with
no pause for the module to release the previous session.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from paradox.connections.ip import connection as ip_connection
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.connection import LocalIPConnection
from paradox.connections.protocol_base import ConnectionProtocol


@pytest.mark.asyncio
async def test_each_failed_attempt_is_closed_and_followed_by_a_pause(mocker):
    connection = LocalIPConnection(host="localhost", port=1000, password="test")

    protocols = []
    for _ in range(3):
        protocol = mocker.Mock(spec=ConnectionProtocol)
        protocol.is_active.return_value = True
        protocol.close = AsyncMock()
        protocols.append(protocol)

    create_connection = AsyncMock(side_effect=[(None, p) for p in protocols])
    mocker.patch.object(
        asyncio.get_event_loop(), "create_connection", create_connection
    )
    mocker.patch.object(
        IPModuleConnectCommand, "execute", AsyncMock(side_effect=asyncio.TimeoutError)
    )
    sleep = mocker.patch.object(ip_connection.asyncio, "sleep", AsyncMock())

    assert await connection.connect() is False

    assert create_connection.await_count == 3
    for protocol in protocols:
        protocol.close.assert_awaited_once()

    assert connection._protocol is None
    assert connection.connected is False

    # Two pauses between three attempts, and none after the last.
    assert sleep.await_args_list == [mocker.call(ip_connection.CONNECT_RETRY_DELAY)] * 2


@pytest.mark.asyncio
async def test_a_successful_connect_is_not_torn_down_or_delayed(mocker):
    connection = LocalIPConnection(host="localhost", port=1000, password="test")

    protocol = mocker.Mock(spec=ConnectionProtocol)
    protocol.is_active.return_value = True
    protocol.close = AsyncMock()

    mocker.patch.object(
        asyncio.get_event_loop(),
        "create_connection",
        AsyncMock(return_value=(None, protocol)),
    )
    mocker.patch.object(IPModuleConnectCommand, "execute", AsyncMock())
    sleep = mocker.patch.object(ip_connection.asyncio, "sleep", AsyncMock())

    assert await connection.connect() is True

    protocol.close.assert_not_awaited()
    sleep.assert_not_awaited()
    assert connection.connected is True
