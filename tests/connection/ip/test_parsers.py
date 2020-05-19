from paradox.connections.ip.parsers import IPMessageRequest, IPMessageResponse


def test_IPMessageRequest_defaults():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageRequest.build(dict(payload=test_payload), password=key)
    print(a)
    data = IPMessageRequest.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_request"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.cryptor_code == 0
    assert data.header.sequence_id == 0
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 0
    assert data.payload == test_payload


def test_IPMessageRequest_cryptor_sequence():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageRequest.build(
        dict(payload=test_payload, header=dict(sequence_id=1, cryptor_code=2)),
        password=key,
    )
    print(a)
    assert a[9] == 2
    assert a[11] == 1

    data = IPMessageRequest.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_request"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 0
    assert data.payload == test_payload


def test_IPMessageResponse_defaults():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageResponse.build(dict(payload=test_payload), password=key)
    print(a)
    data = IPMessageResponse.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_response"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 3
    assert data.payload == test_payload
