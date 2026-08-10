"""Tests for the GSM modem line protocol."""

from unittest import mock

import pytest

from paradox.connections.gsm.protocol import (
    MAX_LINE_LENGTH,
    PROMPT,
    GsmSerialProtocol,
)


# Test GsmSerialProtocol class
@pytest.mark.asyncio
async def test_gsm_serial_protocol():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)

    transport = mock.MagicMock()
    protocol.connection_made(transport)
    handler.on_connection.assert_called_once()

    message = b"test_message"
    protocol.send_message(message)
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

    protocol.send_message(b"AT")
    protocol.data_received(b"AT\r\nOK\r\n")

    handler.on_message.assert_called_once_with(b"OK")


@pytest.mark.asyncio
async def test_gsm_serial_protocol_drops_cr_terminated_echo():
    """Many V.25ter modems echo the command terminated by a bare CR."""
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    protocol.send_message(b"AT")
    protocol.data_received(b"AT\r\r\nOK\r\n")

    handler.on_message.assert_called_once_with(b"OK")


@pytest.mark.asyncio
async def test_gsm_serial_protocol_echo_expectation_is_not_sticky():
    """Echo is off after ATE0, so the expectation must die with the response."""
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    protocol.send_message(b"AT+CUSD=1")
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

    protocol.send_message(b"AT")
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

    protocol.send_message(b"AT")
    protocol.reset_framing()
    protocol.data_received(b"AT\r\n")

    handler.on_message.assert_called_once_with(b"AT")


@pytest.fixture
async def connected_protocol():
    handler = mock.MagicMock()
    protocol = GsmSerialProtocol(handler)
    protocol.connection_made(mock.MagicMock())
    handler.reset_mock()
    return protocol


@pytest.mark.asyncio
async def test_the_sms_prompt_is_surfaced_when_expected(connected_protocol):
    """ "> " carries no terminator, so the framer alone can never emit it."""
    connected_protocol.expect_prompt()

    connected_protocol.data_received(b"\r\n> ")

    connected_protocol.handler.on_message.assert_called_once_with(PROMPT)
    assert connected_protocol.buffer == b""


@pytest.mark.asyncio
async def test_the_sms_prompt_is_ignored_when_not_expected(connected_protocol):
    """Unarmed, "> " is just a line that has not finished arriving."""
    connected_protocol.data_received(b"\r\n> ")

    connected_protocol.handler.on_message.assert_not_called()
    assert connected_protocol.buffer == b"> "


@pytest.mark.asyncio
async def test_the_sms_prompt_expectation_is_one_shot(connected_protocol):
    connected_protocol.expect_prompt()
    connected_protocol.data_received(b"\r\n> ")
    connected_protocol.handler.reset_mock()

    connected_protocol.data_received(b"> ")

    connected_protocol.handler.on_message.assert_not_called()


@pytest.mark.asyncio
async def test_lines_are_still_delivered_while_a_prompt_is_expected(connected_protocol):
    connected_protocol.expect_prompt()

    connected_protocol.data_received(b"+CMTI: 1\r\n> ")

    assert [
        c.args[0] for c in connected_protocol.handler.on_message.call_args_list
    ] == [
        b"+CMTI: 1",
        PROMPT,
    ]


@pytest.mark.asyncio
async def test_a_partial_line_is_not_mistaken_for_a_prompt(connected_protocol):
    connected_protocol.expect_prompt()

    connected_protocol.data_received(b"+CMGS")
    connected_protocol.handler.on_message.assert_not_called()

    connected_protocol.data_received(b": 42\r\n")
    connected_protocol.handler.on_message.assert_called_once_with(b"+CMGS: 42")


@pytest.mark.asyncio
async def test_send_raw_appends_no_terminator(connected_protocol):
    """An SMS body ends with Ctrl-Z; a CRLF would add a blank line to it."""
    connected_protocol.send_raw(b"body\x1a")

    connected_protocol.transport.write.assert_called_once_with(b"body\x1a")


@pytest.mark.asyncio
async def test_reset_framing_disarms_the_prompt(connected_protocol):
    connected_protocol.expect_prompt()
    connected_protocol.reset_framing()

    connected_protocol.data_received(b"\r\n> ")

    connected_protocol.handler.on_message.assert_not_called()
