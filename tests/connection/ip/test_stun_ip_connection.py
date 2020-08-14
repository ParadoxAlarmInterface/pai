import pytest
from asynctest import CoroutineMock

from paradox.connections.ip.connection import StunIPConnection
from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.stun_session import StunSession


@pytest.mark.asyncio
async def test_connect(mocker):
    connection = StunIPConnection(
        site_id="home",
        email="em@em.em",
        panel_serial="7484834",
        password="test"
    )

    protocol = mocker.Mock()
    protocol.is_active.return_value = True

    create_connection_mock = CoroutineMock(return_value=(None, protocol))
    mocker.patch.object(connection.loop, 'create_connection', create_connection_mock)
    connect_command_execute = mocker.patch.object(IPModuleConnectCommand, 'execute', CoroutineMock())

    stun_session_connect = mocker.patch.object(StunSession, 'connect', CoroutineMock())
    stun_session_get_socket = mocker.patch.object(StunSession, 'get_socket', return_value=mocker.Mock())

    assert connection.connected is False

    await connection.connect()

    create_connection_mock.assert_called_once()
    stun_session_connect.assert_called_once()
    connect_command_execute.assert_called_once()
    stun_session_get_socket.assert_called_once()

    assert connection.connected is True