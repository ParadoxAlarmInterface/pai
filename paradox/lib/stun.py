# coding: utf-8

# Adapted from code in https://github.com/konomae/stunpy

import random
import socket
import binascii
import struct

STUN_PORT = 3478

FAMILY_IPv4 = b'\x01'
FAMILY_IPv6 = b'\x02'

# 0b00: Request
# 0b01: Binding
BINDING_REQUEST_SIGN = b'\x00\x01' # 16bit (2bytes)

BINDING_RESPONSE_ERROR = b'\x01\x11'
BINDING_RESPONSE_SUCCESS = b'\x01\x01'
MAGIC_COOKIE = b'\x21\x12\xA4\x42' # 32bit (4bytes)

CHANGE_RESPONSE_SUCCESS = b'\x01\x03'

CONNECT_REQUEST = b'\x00\x0a'
CONNECT_RESPONSE_SUCCESS = b'\x01\x0a'

CONNECTION_BIND_REQUEST = b'\x00\x0b'
CONNECTION_BIND_SUCCESS = b'\x01\x0b'

CONNECTION_REFRESH_REQUEST = b'\x00\x04'

# STUN Attribute Registry
MAPPED_ADDRESS = b'\x00\x01'
RESPONSE_ADDRESS = b'\x00\x02'
CHANGE_REQUEST = b'\x00\x03'
SOURCE_ADDRESS = b'\x00\x04'
CHANGED_ADDRESS = b'\x00\x05'
USERNAME = b'\x00\x06'
PASSWORD = b'\x00\x07'
MESSAGE_INTEGRITY = b'\x00\x08'
ERROR_CODE = b'\x00\x09'
UNKNOWN_ATTRIBUTES = b'\x00\x0A'
REFLECTED_FROM = b'\x00\x0B'
REALM = b'\x00\x14'
NONCE = b'\x00\x15'
XOR_MAPPED_ADDRESS = b'\x80\x82'
XOR_PEER_ADDRESS = b'\x00\x12'
REQUESTED_TRANSPORT = b'\x00\x19'
TRANSPORT_TCP = b'\x06'
LIFETIME = b'\x00\x0d'
REQUESTED_ADDRESS_TYPE = b'\x00\x17'
RESERVED3 = b'\x00\x00\x00'
RESERVED1 = b'\x00'
CONNECTION_ID = b'\x00\x2a'

STUN_ATTRIBUTE_NAMES = {
    MAPPED_ADDRESS: 'MAPPED-ADDRESS',
    RESPONSE_ADDRESS: 'RESPONSE-ADDRESS',
    CHANGE_REQUEST: 'CHANGE-REQUEST',
    SOURCE_ADDRESS: 'SOURCE-ADDRESS',
    CHANGED_ADDRESS: 'CHANGED-ADDRESS',
    USERNAME: 'USERNAME',
    PASSWORD: 'PASSWORD',
    MESSAGE_INTEGRITY: 'MESSAGE-INTEGRITY',
    ERROR_CODE: 'ERROR-CODE',
    UNKNOWN_ATTRIBUTES: 'UNKNOWN-ATTRIBUTES',
    REFLECTED_FROM: 'REFLECTED-FROM',
    REALM: 'REALM',
    NONCE: 'NONCE',
    XOR_MAPPED_ADDRESS: 'XOR-MAPPED-ADDRESS',
    b'\x00\x20': 'XOR-MAPPED-ADDRESS',
}

def generate_transaction_id():
    tid = []
    for i in range(24): # 96bits (12bytes)
        tid.append(random.choice('0123456789ABCDEF'))
    return binascii.a2b_hex(''.join(tid))


def build_binding_request(transaction_id):
    if len(transaction_id) != 12:
        raise Exception('Invalid transaction id')

    body_length = b'\x00\x00'
    return b''.join([BINDING_REQUEST_SIGN, body_length, MAGIC_COOKIE, transaction_id])

def build_change_request(transaction_id):
    if len(transaction_id) != 12:
        raise Exception('Invalid transaction id')

    body_length = b'\x00\x18'
    return b''.join([CHANGE_REQUEST, body_length, MAGIC_COOKIE, transaction_id, 
                REQUESTED_TRANSPORT, b'\x00\x04', TRANSPORT_TCP, RESERVED3,
                LIFETIME, b'\x00\x04', b'\x00\x00\x02\x58',
                REQUESTED_ADDRESS_TYPE, b'\x00\x04', FAMILY_IPv4, RESERVED3 ])

def build_connection_bind_request(transaction_id, connection_id):
    if len(transaction_id) != 12:
        raise Exception('Invalid transaction id')

    if len(connection_id) != 4:
        raise Exception('Invalid connection id {}'.format(len(connection_id)))

    body_length = b'\x00\x08'
    return b''.join([CONNECTION_BIND_REQUEST, body_length, MAGIC_COOKIE, transaction_id,
        CONNECTION_ID, b'\x00\x04', connection_id])

def build_connection_refresh_request(transaction_id):
    if len(transaction_id) != 12:
        raise Exception('Invalid transaction id')

    body_length = b'\x00\x08'
    return b''.join([CONNECTION_REFRESH_REQUEST, body_length, MAGIC_COOKIE, transaction_id,
        LIFETIME, b'\x00\x04', b'\x00\x00\x02\x58'])

def build_connect_request(transaction_id,xoraddr=None):
    if len(transaction_id) != 12:
        raise Exception('Invalid transaction id')

    if xoraddr is None:
        raise Exception("Invalid connect address")

    body_length = b'\x00\x0c'
    return b''.join([CONNECT_REQUEST, body_length, MAGIC_COOKIE, transaction_id, 
                XOR_PEER_ADDRESS, b'\x00\x08', xoraddr])

def validate_response(buf, transaction_id):
    if not buf or len(buf) < 20:
        raise Exception('Response too short')

    response_magic_cookie = buf[4:8]
    if MAGIC_COOKIE != response_magic_cookie:
        raise Exception('Invalid magic cookie')

    response_transaction_id = buf[8:20]
    if transaction_id != response_transaction_id:
        raise Exception('invalid transaction id')


def ip_to_bytes(ip, xor):
    octets = [binascii.a2b_hex('%02x' % int(o)) for o in ip.split('.')]
    addr_int = struct.unpack('!I', b''.join(octets))[0]

    if xor:
        magicCookieBytesInt = int(binascii.b2a_hex(MAGIC_COOKIE), 16)
        addr_int = magicCookieBytesInt ^ addr_int

    addr_bytes = binascii.a2b_hex('%08x' % addr_int)
    return addr_bytes


def port_to_bytes(port, xor):
    if xor:
        magicCookieHighBytesInt = int(binascii.b2a_hex(MAGIC_COOKIE[:2]), 16)
        port = magicCookieHighBytesInt ^ port

    port_bytes = binascii.a2b_hex('%04x' % port)
    return port_bytes


def read_mapped_address(attr_type, attr_body, attr_len):
    assert attr_type in (MAPPED_ADDRESS, XOR_MAPPED_ADDRESS, b'\x00\x20')
    assert attr_body[:1] == b'\x00'

    family_bytes = attr_body[1:2]
    port_bytes = attr_body[2:4]
    addr_bytes = attr_body[4:attr_len]
    xor = attr_type in (XOR_MAPPED_ADDRESS, b'\x00\x20')

    family_text = ''
    assert family_bytes in (FAMILY_IPv4, FAMILY_IPv6)
    if family_bytes == FAMILY_IPv4:
        family_text = 'IPv4'
    elif family_bytes == FAMILY_IPv6:
        family_text = 'IPv6'

    # TODO: IPv6s
    port = int(binascii.b2a_hex(port_bytes), 16)
    addr_int = int(binascii.b2a_hex(addr_bytes), 16)

    if xor:
        # port
        magicCookieHighBytesInt = int(binascii.b2a_hex(MAGIC_COOKIE[:2]), 16)
        port =  magicCookieHighBytesInt ^ port

        # addr
        magicCookieBytesInt = int(binascii.b2a_hex(MAGIC_COOKIE), 16)
        addr_int =  magicCookieBytesInt ^ addr_int

    octets = struct.pack('!I', addr_int)
    ip = '.'.join([str(c) for c in octets])
    return dict(name=STUN_ATTRIBUTE_NAMES[attr_type], ip=ip, port=port, family=family_text)


def read_attributes(attributes, body_length):
    pos = 0
    parsed_attributes = []
    while pos < body_length:
        attr_type = attributes[pos:pos + 2] # 16bit (2bytes)
        attr_len = int(binascii.b2a_hex(attributes[pos + 2:pos + 4]), 16) # 16bit (2bytes)
        attr_body = attributes[pos + 4:pos + 4 + attr_len]

        if attr_type in (MAPPED_ADDRESS, XOR_MAPPED_ADDRESS, b'\x00\x20'):
            parsed_attributes.append(read_mapped_address(attr_type, attr_body, attr_len))
        else:
            if attr_type == b'\x80\x22':
                attr_body = attr_body.decode('utf-8')
            else:
                attr_body = attr_body.hex()
            parsed_attributes.append(dict(
                name=STUN_ATTRIBUTE_NAMES.get(attr_type),
                attr_type=attr_type.hex(),
                attr_body=attr_body,
                attr_len=attr_len
            ))

        attr_head = (2 + 2) # attr_type + attr_len
        remain = attr_len % 4
        padding = 4 - remain if remain else 0
        pos += attr_head + attr_len + padding

    return parsed_attributes


def is_error(body):
    for element in body:
        if element['name'] == 'ERROR-CODE':
            return True

    return False


def get_error(body):
    for element in body:
        if element['name'] == 'ERROR-CODE':
            body = binascii.unhexlify(element['attr_body'])
            return {'class': body[:3], 'code': body[3], 'reason': body[4:]}

    return False

    

class StunClient(object):
    def __init__(self, host, port=STUN_PORT):
        self.sock = None
        self.transaction_id = None
        self.req = None
        self.transaction_id = generate_transaction_id()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', 0))
        self.host = host
        self.port = port
        self.sock.connect( (host, port))

    def send_tcp_change_request(self):
        self.req = build_change_request(self.transaction_id)
        self.sock.send(self.req)
        
    def send_binding_request(self):
        self.req = build_binding_request(self.transaction_id)
        self.sock.send(self.req)

    def send_connect_request(self, host=None, port=None, xoraddr=None):
        if host is not None and port is not None:
            xorhost = ip_to_bytes(host, True)
            xorport = port_to_bytes(port, True)
            addr = b''.join([xorport, xorhost])
        elif xoraddr is not None:
            addr = xoraddr
        else:
            raise Exception("Invalid arguments") 
        
        self.req = build_connect_request(self.transaction_id, addr)
        self.sock.send(self.req)

    def send_connection_bind_request(self, connection_id):
        self.req = build_connection_bind_request(self.transaction_id, connection_id)
        self.sock.send(self.req)

    def receive_response(self):
        buf = self.sock.recv(2048)
        validate_response(buf, self.transaction_id)

        body_length = int(binascii.b2a_hex(buf[2:4]), 16)
        attributes = buf[20:]
        assert len(attributes) == body_length

        return read_attributes(attributes, body_length)

    def send_refresh_request(self):
        self.req = build_connection_refresh_request(self.transaction_id)
        self.sock.send(self.req)

    def get_socket(self):
        return self.sock

    def close(self):
        if self.sock:
            self.sock.close()

