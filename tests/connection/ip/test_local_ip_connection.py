import pytest
from asynctest import CoroutineMock

from paradox.connections.ip.connection import LocalIPConnection
from paradox.connections.ip.commands import IPModuleConnectCommand


class TestProtocol:
    def is_active(self):
        return True


@pytest.mark.asyncio
async def test_connect(mocker):
    connection = LocalIPConnection(
        host="localhost",
        port=1000,
        password="test"
    )

    create_connection_mock = CoroutineMock(return_value=(None, TestProtocol()))
    mocker.patch.object(connection.loop, 'create_connection', create_connection_mock)
    connect_command_execute = mocker.patch.object(IPModuleConnectCommand, 'execute', CoroutineMock())

    assert connection.connected is False

    await connection.connect()

    create_connection_mock.assert_called_once()
    connect_command_execute.assert_called_once()

    assert connection.connected is True