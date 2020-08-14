import pytest
from asynctest import CoroutineMock

from paradox.connections.ip.connection import BareIPConnection
from paradox.connections.protocols import ConnectionProtocol


@pytest.mark.asyncio
async def test_connect(mocker):
    connection = BareIPConnection(
        host="localhost",
        port=1000
    )

    protocol = mocker.Mock(spec=ConnectionProtocol)
    protocol.is_active.return_value = True

    create_connection_mock = CoroutineMock(return_value=(None, protocol))
    mocker.patch.object(connection.loop, 'create_connection', create_connection_mock)

    assert connection.connected is False

    await connection.connect()

    create_connection_mock.assert_called_once()

    assert connection.connected is True