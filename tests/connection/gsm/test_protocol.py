"""Tests for the GSM modem line protocol."""

from unittest import mock

import pytest

from paradox.connections.gsm.protocol import MAX_LINE_LENGTH, GsmSerialProtocol


# Test GsmSerialProtocol class
@pytest.mark.asyncio
async def test_gsm_serial_protocol():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)

    transport = mock.MagicMock()
    protocol.connection_made(transport)
    handler.on_connection.assert_called_once()

    message = b"test_message"
    await protocol.send_message(message)
    transport.write.assert_called_once_with(message + b"\r\n")

    recv_data = b"test_data\r\n"
    protocol.data_received(recv_data)
    handler.on_message.assert_called_once_with(b"test_data")

    exc = Exception("test_exception")
    protocol.connection_lost(exc)
    handler.on_connection_loss.assert_called_once_with()


@pytest.mark.asyncio
async def test_gsm_serial_protocol_reassembles_split_frames():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    protocol.data_received(b"par")
    handler.on_message.assert_not_called()

    protocol.data_received(b"tial\r\n\r\nOK\r\ntrail")

    assert handler.on_message.call_args_list == [
        mock.call(b"partial"),
        mock.call(b"OK"),
    ]
    assert protocol.buffer == b"trail"

    protocol.reset_framing()
    assert protocol.buffer == b""


@pytest.mark.asyncio
async def test_gsm_serial_protocol_drops_echoed_message():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT")
    protocol.data_received(b"AT\r\nOK\r\n")

    handler.on_message.assert_called_once_with(b"OK")


@pytest.mark.asyncio
async def test_gsm_serial_protocol_drops_cr_terminated_echo():
    """Many V.25ter modems echo the command terminated by a bare CR."""
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT")
    protocol.data_received(b"AT\r\r\nOK\r\n")

    handler.on_message.assert_called_once_with(b"OK")


@pytest.mark.asyncio
async def test_gsm_serial_protocol_echo_expectation_is_not_sticky():
    """Echo is off after ATE0, so the expectation must die with the response."""
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT+CUSD=1")
    protocol.data_received(b"OK\r\n")
    protocol.data_received(b"AT+CUSD=1\r\n")

    assert handler.on_message.call_args_list == [
        mock.call(b"OK"),
        mock.call(b"AT+CUSD=1"),
    ]


@pytest.mark.asyncio
async def test_gsm_serial_protocol_only_checks_the_first_frame_for_echo():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT")
    protocol.data_received(b"OK\r\nAT\r\n")

    assert handler.on_message.call_args_list == [mock.call(b"OK"), mock.call(b"AT")]


def test_gsm_serial_protocol_keeps_draining_after_a_callback_raises():
    handler = mock.MagicMock()
    handler.on_message.side_effect = [ValueError("bad line"), None]
    protocol = GsmSerialProtocol(handler)

    protocol.data_received(b"\xff\r\nOK\r\n")

    assert handler.on_message.call_args_list == [mock.call(b"\xff"), mock.call(b"OK")]
    assert protocol.buffer == b""


def test_gsm_serial_protocol_discards_an_oversized_partial_frame():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)

    protocol.data_received(b"x" * (MAX_LINE_LENGTH + 1))

    handler.on_message.assert_not_called()
    assert protocol.buffer == b""


def test_gsm_serial_protocol_keeps_a_whitespace_only_line():
    """An SMS body of a single space is data, not framing noise."""
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)

    protocol.data_received(b" \r\n")

    handler.on_message.assert_called_once_with(b" ")


@pytest.mark.asyncio
async def test_gsm_serial_protocol_reset_framing_clears_echo_expectation():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT")
    protocol.reset_framing()
    protocol.data_received(b"AT\r\n")

    handler.on_message.assert_called_once_with(b"AT")
