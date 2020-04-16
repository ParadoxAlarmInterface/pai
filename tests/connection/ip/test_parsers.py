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
    assert data.header.flags.encrypt == True
    assert data.header.flags.other == 4
    assert data.header.command == "panel_communication"
    assert data.header.unknown1 == 0
    assert data.header.unknown2 == 0
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
    assert data.header.flags.encrypt == True
    assert data.header.flags.other == 4
    assert data.header.command == "panel_communication"
    assert data.header.unknown1 == 0
    assert data.header.unknown2 == 3
    assert data.payload == test_payload
