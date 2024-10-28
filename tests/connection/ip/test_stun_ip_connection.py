import asyncio
from unittest.mock import AsyncMock

import pytest

from paradox.connections.ip.commands import IPModuleConnectCommand
from paradox.connections.ip.connection import StunIPConnection
from paradox.connections.ip.stun_session import StunSession


@pytest.mark.asyncio
async def test_connect(mocker):
    connection = StunIPConnection(
        site_id="home", email="em@em.em", panel_serial="0584b067", password="test"
    )

    protocol = mocker.Mock()
    protocol.is_active.return_value = True

    create_connection_mock = AsyncMock(return_value=(None, protocol))
    mocker.patch.object(
        asyncio.get_event_loop(), "create_connection", create_connection_mock
    )
    connect_command_execute = mocker.patch.object(
        IPModuleConnectCommand, "execute", AsyncMock()
    )

    stun_session_connect = mocker.patch.object(StunSession, "connect", AsyncMock())
    stun_session_get_socket = mocker.patch.object(
        StunSession, "get_socket", return_value=mocker.Mock()
    )

    assert connection.connected is False

    await connection.connect()

    create_connection_mock.assert_called_once()
    stun_session_connect.assert_called_once()
    connect_command_execute.assert_called_once()
    stun_session_get_socket.assert_called_once()

    assert connection.connected is True


@pytest.mark.asyncio
async def test_connect_with_panel_serial(mocker):
    session = StunSession(site_id="home", email="em@em.em", panel_serial="0584b067")

    json_data = await assert_session_connect(mocker, session)

    assert session.connection_timestamp != 0
    assert session.module == json_data["site"][0]["module"][3]


@pytest.mark.asyncio
async def test_connect_without_panel_serial(mocker):
    session = StunSession(site_id="home", email="em@em.em", panel_serial=None)

    json_data = await assert_session_connect(mocker, session)

    assert session.connection_timestamp != 0
    assert session.module == json_data["site"][0]["module"][2]


async def assert_session_connect(mocker, session):
    json_data = {
        "site": [
            {
                "name": "pai-site",
                "module": [
                    {
                        "lastUpdate": "2021-05-07T15:41:19Z",
                        "mac": "dbb2604a6c5a",
                        "API": None,
                        "name": "Playroom",
                        "ipAddress": "1.0.0.127",
                        "serial": "bf4c1fe4",
                        "type": "HD77",
                        "port": 54321,
                        "panelSerial": "0584b067",
                    },
                    {
                        "lastUpdate": "2021-05-07T15:41:19Z",
                        "mac": "d1c9f2af99c0",
                        "API": None,
                        "name": "Outdoors",
                        "ipAddress": "1.0.0.127",
                        "serial": "465e81a0",
                        "type": "HD88",
                        "port": 12345,
                        "panelSerial": "0584b067",
                    },
                    {
                        "lastUpdate": "2021-05-07T15:41:19Z",
                        "mac": "1bf03fb38cfa",
                        "serial": "665e91e7",
                        "port": 56789,
                        "swport": 10000,
                        "name": None,
                        "type": "IP150",
                        "panelSerial": "a72ed4bf",
                        "xoraddr": "9a640069cda9b317",
                        "API": None,
                        "ipAddress": "0.0.0.0",
                    },
                    {
                        "lastUpdate": "2021-05-07T15:41:19Z",
                        "mac": "227b020bcda7",
                        "serial": "0bca8766",
                        "port": 98765,
                        "swport": 10000,
                        "name": None,
                        "type": "IP150",
                        "panelSerial": "0584b067",
                        "xoraddr": "c351472f48a5e1ba",
                        "API": None,
                        "ipAddress": "0.0.0.0",
                    },
                ],
                "paid": 1,
                "daysLeft": 364,
                "sitePanelStatus": 1,
                "email": "em@em.com",
            }
        ]
    }

    class StubResponse:
        status_code = 200

        def json(self):
            return json_data

    mocker.patch("requests.get").return_value = StubResponse()
    client = mocker.patch("paradox.lib.stun.StunClient")
    client.return_value.receive_response.return_value = [
        {"attr_body": "abcdef", "name": "BEER"}
    ]
    await session.connect()
    return json_data
