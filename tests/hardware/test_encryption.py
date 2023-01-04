import pytest
from construct import (Struct, BitStruct, Const, Nibble, Flag, Int8ub, Int16ub, Bytes, Array, Checksum, this, RawCopy)
from paradox.hardware.evo.parsers import CompressedEvent, PacketLength, calculate_checksum

Encrypted = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xE, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "source" / Const(0xFE, Int8ub),
            "length" / PacketLength(Int8ub),
            "_not_used0" / Bytes(1),
            "request_nr" / Int8ub,
            "data" / Bytes(lambda this: this.length - 7)
        )
    ),
    "checksum"
    / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data),
    "end" / Int8ub,
)


@pytest.mark.parametrize(
    "payload_hex",
    [
        # from EVO192 7.50.000+ firmware
        # tx
        ("E0 FE 2E 00 12 C5 CA 4A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 52 CC 91 19"),
        # rx
        ("E0 FE 2E 00 12 C5 3F 0A B7 DC 83 97 D4 06 F6 E9 EB 47 56 5C 89 38 BF 35 F0 EA A5 DC C3 2B 95 D2 80 E9 B3 EE 36 9B E2 17 50 FD B4 CC 7C 19"),
        # tx
        ("E0 FE 2E 00 12 01 79 71 35 21 C7 F1 C5 3F 0A B7 DC B3 E5 D0 46 E6 E9 F9 E3 72 FA C8 38 3F 06 56 E6 13 DD D3 AB B4 D0 88 BB B3 77 B4 11 19"),
        # rx
        ("E0 FE 0F 00 12 01 3D 77 35 21 F7 03 B4 B8 04"),
        ("E0 FE 2E 00 13 80 4F F6 7E FD 6A 3B 91 85 52 E2 45 A5 52 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC E0 69 9B 16"),
        ("E0 FE 2E 00 14 61 CB D8 54 3E 81 E5 F1 2B BC E0 EE BB B2 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 28 D3 4A 18"),
        # tx
        ("E0 FE 11 00 14 F5 78 3D 21 F7 59 83 BF 54 BC 70 07"),
        # rx
        ("E0 FE 50 00 14 F5 7A 90 21 F7 59 83 0F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 8E 81 F7 D4 49 FC 06 BE 6E E3 4E 29 99 BC E5 2A"),
        # tx
        ("E0 FE 11 00 14 E3 42 95 95 56 5A DB 25 19 8C A7 06"),
        # rx
        ("E0 FE 50 00 14 E3 40 38 95 56 5A DB A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 B3 A3 FE B6 8B E2 17 50 ED 07 15 F3 05 D7 2F B5 F1 8C FD 29"),
        # tx
        ("E0 FE 11 00 14 A8 76 23 8A F9 6A EF 5A E3 24 81 07"),
        # rx
        ("E0 FE 50 00 14 A8 74 8E 8A F9 6A EF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 B5 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 16 24 69 2A"),
        # tx
        ("E0 FE 11 00 14 B7 E4 97 24 7F E4 CE FB 4F B8 8C 08"),
        # rx
        ("E0 FE 50 00 14 B7 F4 0A 24 7F E4 CE F9 90 CF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 25 B8 72 2A"),
        # tx
        ("E0 FE 11 00 14 F7 BC 57 EC F4 65 C7 A4 1F 84 60 08"),
        # rx
        ("E0 FE 50 00 14 F7 BE FA EC F4 65 C7 24 7F 2B 8A F9 90 CF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD A3 84 C3 2A"),
        # tx
        ("E0 FE 11 00 14 F9 3F 57 79 71 8F C8 26 F8 10 01 07"),
        # rx
        ("E0 FE 4C 00 14 F9 2F 4A 79 71 8F C8 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 8E 81 F7 D4 49 5D 10 7E 28"),
        # from SP6000+
        ("e0 fe 2e 00 00 78 04 c1 92 06 f6 e9 eb 47 76 1e c9 28 bf 27 54 ee 41 dd d3 ab b4 d0 88 bb b3 ee 36 9b e2 17 50 fd 2d 15 f3 05 20 6b 7f 16")
    ],
)
def test_parse(payload_hex: str):
    payload = bytes.fromhex(payload_hex)
    data = Encrypted.parse(payload)
    print(f"Expected length: {len(payload[5:-2])}, actual length: {len(data.fields.value.data)}")
    assert data.fields.value.data == payload[5:-2]
    print(data)

# def test_payload_decryption():
#     payload = bytes.fromhex("12 01 3D 77 35 21 F7 03 B4")
#     l = len(payload)
#     print(f"Length: {l}")
