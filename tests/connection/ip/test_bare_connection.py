import pytest
from asynctest import CoroutineMock

from paradox.connections.ip.connection import BareIPConnection


class DummyProtocol:
    def is_active(self):
        return True


@pytest.mark.asyncio
async def test_connect(mocker):
    connection = BareIPConnection(
        host="localhost",
        port=1000
    )

    create_connection_mock = CoroutineMock(return_value=(None, DummyProtocol()))
    mocker.patch.object(connection.loop, 'create_connection', create_connection_mock)

    assert connection.connected is False

    await connection.connect()

    create_connection_mock.assert_called_once()

    assert connection.connected is True