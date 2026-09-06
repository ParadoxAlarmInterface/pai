"""Closing must drop the connection's state even when it fails.

``ConnectionProtocol.close()`` awaits the transport's closed future, which
carries an *exception* whenever the link died with one -- the normal case when
closing after a fault. It can also time out waiting for the transport to
settle. The state reset used to sit after that await, so a raising close left
``_protocol`` pointing at a dead protocol for the next connect attempt to
inherit.
"""

from unittest.mock import AsyncMock

import pytest

from paradox.connections.connection import Connection
from paradox.connections.protocol_base import ConnectionProtocol


class _Connection(Connection):
    async def connect(self) -> bool:
        return True


def _connected(mocker, close_side_effect=None):
    connection = _Connection()
    protocol = mocker.Mock(spec=ConnectionProtocol)
    protocol.is_active.return_value = True
    protocol.close = AsyncMock(side_effect=close_side_effect)
    connection._protocol = protocol
    connection.connected = True
    return connection


@pytest.mark.asyncio
async def test_close_resets_state_when_the_protocol_raises(mocker):
    connection = _connected(mocker, ConnectionResetError("connection reset by peer"))

    with pytest.raises(ConnectionResetError):
        await connection.close()

    assert connection._protocol is None
    assert connection.connected is False


@pytest.mark.asyncio
async def test_close_resets_state_on_a_clean_close(mocker):
    connection = _connected(mocker)

    await connection.close()

    assert connection._protocol is None
    assert connection.connected is False


@pytest.mark.asyncio
async def test_close_is_idempotent():
    connection = _Connection()

    await connection.close()

    assert connection._protocol is None
    assert connection.connected is False
