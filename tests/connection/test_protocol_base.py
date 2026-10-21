"""Tests for the shared asyncio protocol base."""

import asyncio

import pytest

from paradox.connections.handler import ConnectionHandler
from paradox.connections.protocol_base import ConnectionProtocol


class DummyProtocol(ConnectionProtocol):
    def send_message(self, message):
        self.transport.write(message)


@pytest.fixture
def handler(mocker):
    return mocker.MagicMock(spec=ConnectionHandler)


@pytest.fixture
def transport(mocker):
    return mocker.MagicMock()


@pytest.fixture
async def protocol(handler, transport):
    p = DummyProtocol(handler)
    p.connection_made(transport)
    return p


def test_abstract_send_message_blocks_instantiation(handler):
    class Incomplete(ConnectionProtocol):
        pass

    with pytest.raises(TypeError):
        Incomplete(handler)


def test_concrete_subclass_instantiates(handler):
    assert DummyProtocol(handler) is not None


async def test_connection_made_notifies_handler(protocol, handler):
    handler.on_connection.assert_called_once()


async def test_is_active_after_connection_made(protocol):
    assert protocol.is_active() is True


def test_is_active_false_before_connection_made(handler):
    assert DummyProtocol(handler).is_active() is False


def test_check_active_raises_when_inactive(handler):
    with pytest.raises(ConnectionError):
        DummyProtocol(handler).check_active()


async def test_check_active_passes_when_active(protocol):
    protocol.check_active()


async def test_connection_lost_cleanly_resolves_closed(protocol, handler):
    protocol.connection_lost(None)
    handler.on_connection_loss.assert_called_once()
    assert protocol.is_active() is False


async def test_connection_lost_with_error_sets_exception(handler, transport):
    p = DummyProtocol(handler)
    p.connection_made(transport)
    error = ConnectionResetError("boom")
    p.connection_lost(error)
    with pytest.raises(ConnectionResetError):
        await p.close()


async def test_close_waits_for_connection_lost(protocol):
    loop = asyncio.get_running_loop()
    loop.call_soon(protocol.connection_lost, None)
    await protocol.close()
    assert protocol.transport is None


async def test_close_is_safe_before_connection_made(handler):
    await DummyProtocol(handler).close()


async def test_clean_close_is_not_logged_as_an_error(protocol, caplog):
    protocol.connection_lost(None)
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


async def test_unexpected_close_is_logged_as_an_error(protocol, caplog):
    protocol.connection_lost(ConnectionResetError("boom"))
    assert [r for r in caplog.records if r.levelname == "ERROR"]


async def test_base_reports_variable_message_length_by_default(protocol):
    assert protocol.use_variable_message_length is True


async def test_base_variable_message_length_is_a_no_op(protocol):
    protocol.variable_message_length(False)
