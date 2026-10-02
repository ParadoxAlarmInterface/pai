"""STUN runs over TCP, which does not preserve message boundaries.

``receive_response`` used to assert that a single ``recv()`` returned the whole
message, so ordinary segmentation surfaced as an unexplained connect failure.
The sockets also had no timeout: a TURN server that stopped answering blocked
the caller forever, and the session refresh used to run on the event loop.
"""

import pytest

from paradox.lib import stun


class _SegmentedSocket:
    """Hands back at most ``chunk_size`` bytes per recv(), like a busy link."""

    def __init__(self, payload, chunk_size):
        self._payload = payload
        self._chunk_size = chunk_size
        self.reads = 0

    def recv(self, length):
        self.reads += 1
        take = min(length, self._chunk_size)
        chunk, self._payload = self._payload[:take], self._payload[take:]
        return chunk


def _client(payload, chunk_size):
    client = stun.StunClient.__new__(stun.StunClient)
    client.sock = _SegmentedSocket(payload, chunk_size)
    client.transaction_id = b"T" * 12
    return client


def test_recv_exactly_reassembles_a_segmented_read():
    client = _client(b"0123456789", chunk_size=3)

    assert client._recv_exactly(10) == b"0123456789"
    assert client.sock.reads == 4


def test_recv_exactly_raises_when_the_peer_closes_early():
    client = _client(b"012", chunk_size=3)

    with pytest.raises(Exception, match="Connection closed"):
        client._recv_exactly(10)


def test_receive_response_reassembles_a_split_header():
    header = (
        stun.BINDING_RESPONSE_SUCCESS  # message type
        + b"\x00\x00"  # body length: no attributes
        + stun.MAGIC_COOKIE
        + b"T" * 12  # transaction id
    )
    client = _client(header, chunk_size=7)

    assert client.receive_response() == []
    # The 20 byte header took three reads; a single recv() would have truncated
    # it and tripped the old length assertion.
    assert client.sock.reads == 3


def test_receive_response_rejects_a_foreign_transaction_id():
    header = (
        stun.BINDING_RESPONSE_SUCCESS
        + b"\x00\x00"
        + stun.MAGIC_COOKIE
        + b"X" * 12  # not the client's transaction id
    )
    client = _client(header, chunk_size=20)

    with pytest.raises(Exception, match="invalid transaction id"):
        client.receive_response()


def test_stun_client_bounds_blocking_socket_operations(mocker):
    sock = mocker.Mock()
    mocker.patch.object(stun.socket, "socket", return_value=sock)

    stun.StunClient(host="turn.example.com")

    sock.settimeout.assert_called_once_with(stun.STUN_SOCKET_TIMEOUT)
