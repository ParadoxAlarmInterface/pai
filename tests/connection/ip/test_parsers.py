from paradox.connections.ip.parsers import IPMessageRequest, IPMessageResponse


def test_IPMessageRequest_defaults():
    a = IPMessageRequest.build(dict(header=dict(length=0), payload=b""))
    data = IPMessageRequest.parse(a)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_request"
    assert data.header.length == 0
    assert data.header.flags.encrypt == True
    assert data.header.flags.other == 4
    assert data.header.command == "panel_communication"
    assert data.header.unknown1 == 0
    assert data.header.unknown2 == 0


def test_IPMessageResponse_defaults():
    a = IPMessageResponse.build(dict(header=dict(length=0), payload=b""))
    data = IPMessageResponse.parse(a)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_response"
    assert data.header.length == 0
    assert data.header.flags.encrypt == True
    assert data.header.flags.other == 4
    assert data.header.command == "panel_communication"
    assert data.header.unknown1 == 0
    assert data.header.unknown2 == 3
