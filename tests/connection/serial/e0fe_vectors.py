"""Synthetic ``E0 FE`` session shared by the E0 FE protocol and session tests.

Panel fields, serial number and password are invented. The wrapped frames were
produced by an independent implementation of the wrapping, not by the code
under test. The panel frames carry seq/seed values of their own, so a client
that did not adopt them would transmit different bytes.
"""


def h(hex_string: str) -> bytes:
    return bytes.fromhex(hex_string)


PASSWORD = "5678"

INITIATE = h("72" + "00" * 35 + "72")
# EVO192, firmware 7.86.001, serial 3e71c492; byte 35 is 0xa0.
IDENTIFY = h(
    "72ff04020000a15a010786013e71c492030202040b1106182a1dff0045564f31" "393200a0b7"
)
# The identify echo: IDENTIFY with byte 35 0xba.
ECHO = h("72ff04020000a15a010786013e71c492030202040b1106182a1dff0045564f31393200bad1")
# The panel's answer to the echo: same bytes, byte 35 zero.
ANSWER = h("72ff04020000a15a010786013e71c492030202040b1106182a1dff0045564f313932000017")
START_REPLY = h(
    "00000000050786006c3d00000b000000003e71c4926203032504411a05000000" "000000003c"
)
# START_REPLY with PASSWORD in bytes 10-11.
LOGIN = h("00000000050786006c3d56780b000000003e71c4926203032504411a05000000000000000a")
LOGIN_OK = h("120600000018")
EVENT_A = h(
    "e2ff02a7141a0603091e2d000300000000000000000000000000000000000000" "0000000018"
)
EVENT_B = h(
    "e2ff02a8141a0603091f2d000200000000000000000000000000000000000000" "0000000019"
)
READ_RAM16 = h("5008800000104028")
RAM16 = h(
    "5247800000100000004100000000000000000000000000080000000000000000"
    "0000000000000000000000000000900000000000000000000000000000000000"
    "00000000000002"
)
CLOSE = h("70040579")
CLOSE_ACK = h("7204057b")

# Client frames, in session order.
TX_ECHO = h(
    "e0fe2e00002f9d43a847f708d33e1fd8b877a41de4d549599b2b8856379ee4f5"
    "737dd1ab90aee7551d5ab500c015"
)
TX_START = h(
    "e0fe2e0006720941fc06be6ee34e2988dd57dd959bb8470abf9316fa445ff437"
    "6326607bb55facf46587d93b7015"
)
TX_LOGIN = h(
    "e0fe2e000915cfda3db2913d64bcc637ba30f2a0dfa546c49c6dc5dbcc76d3d9"
    "980ecf79713521f7a3835fe46318"
)
TX_READ_RAM16 = h("e0fe11000c158bfabdb283087fae510d07")
TX_CLOSE = h("e0fe0d000ea192d0ec542a6605")

# Panel frames, in session order.
RX_EVENT_A = h(
    "e0fe2e000226b14a5b76e5d506744f2419f9c0cfda3db283097ebc6f4b9d9556"
    "a0dfa546db28775ddc9c4c8caa15"
)
RX_ANSWER = h(
    "e0fe2e00063293b6f802be6eaf1b399e984708503ffe550eb78366b20577e804"
    "9c26ecbe82cd1db16587713b0614"
)
RX_START_REPLY = h(
    "e0fe2e000915cfda3db2913d64bcc6379d95f2a0dfa546c49c6dc5dbcc76d3d9"
    "980ecf79713521f7a38312e45e18"
)
RX_LOGIN_OK = h("e0fe0f000c158e9b3db28388518205")
RX_EVENT_B = h(
    "e0fe2e0003c2ea2b091c05977ab3565cfcdd5fdd959bb8470abf9316fa445ff4"
    "376326607bb55facf465dfc72716"
)
RX_RAM16 = h(
    "e0fe50000ea186ddff2d15d305d72f25591960fc6bf3cc76b88e81f7d469fc06"
    "be6ee34e2988dd57dd959bb8470abf9316fa445fb6376326607bb55facf46587"
    "247f2b8af990cfda3db283096e2ada27"
)
RX_CLOSE_ACK = h("e0fe0d0010a3277aa1e1955605")

# EVENT_A sent with seq 0x2a, seed 0x1f; READ_RAM16 sent after it.
RX_EVENT_ELSEWHERE = h(
    "e0fe2e002a25f85a440e0af24fd5ac4adbdb9ebe4779713521f7a3833f0ab7dc"
    "b3c59206f6e9eb47761eed1f6816"
)
TX_READ_RAM16_ELSEWHERE = h("e0fe11002a259b85c6db28765cce1fe606")

# RX_EVENT_A with the wrapped message's own checksum broken; the frame
# checksum is valid.
RX_BAD_INNER_CHECKSUM = h(
    "e0fe2e000226b14a5b76e5d506744f2419f9c0cfda3db283097ebc6f4b9d9556"
    "a0dfa546db28775ddc9c5c8cba15"
)

# IDENTIFY with firmware 7.90.002, and its echo.
IDENTIFY_OTHER_FIRMWARE = h(
    "72ff04020000a15a010790023e71c492030202040b1106182a1dff0045564f31" "393200a0c2"
)
TX_ECHO_OTHER_FIRMWARE = h(
    "e0fe2e00002f9d43a847f708d33e1fd8ad27a41de4d549599b2b8856379ee4f5"
    "737dd1ab90aee7551d5a3c00ec14"
)
# In place of RX_ANSWER: IDENTIFY itself (byte 35 0xa0), wrapped.
RX_ANSWER_WRONG = h(
    "e0fe2e00063293b6f802be6eaf1b399e984708503ffe550eb78366b20577e804"
    "9c26ecbe82cd1db165a57b3b2e14"
)
# In place of RX_LOGIN_OK: the login refused, START_REPLY sent back.
RX_LOGIN_REFUSED = h(
    "e0fe2e000c15cfda3db2913d64bcc6379d95f2a0dfa546c49c6dc5dbcc76d3d9"
    "980ecf79713521f7a3831251ce17"
)
TX_CLOSE_AFTER_REFUSAL = h("e0fe0d000c1589db290851f203")
