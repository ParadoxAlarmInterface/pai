from construct import Checksum, Enum, ExprAdapter, Int8ub, Rebuild, this


def calculate_checksum(message):
    r = 0
    for c in message:
        r += c
    r = r % 256
    return bytes([r])


def _hex_to_int(obj, path):
    try:
        return int(hex(obj)[2:], 10)
    except ValueError:
        return -1


def PacketLength(subcons):
    return Rebuild(
        subcons,
        lambda x: x._root._subcons.fields.sizeof() + x._root._subcons.checksum.sizeof(),
    )


def PacketChecksum(subcons):
    return Checksum(subcons, lambda data: calculate_checksum(data), this.fields.data)


HexInt = ExprAdapter(Int8ub, _hex_to_int, lambda obj, path: int(str(obj), 16))

ProductIdEnum = Enum(
    Int8ub,
    DIGIPLEX_v13=0,
    DIGIPLEX_v2=1,
    DIGIPLEX_NE=2,
    DIGIPLEX_EVO_48=3,
    DIGIPLEX_EVO_96=4,
    DIGIPLEX_EVO_192=5,
    DIGIPLEX_EVO_HD=7,
    DIGIPLEX_EVO_HD_PLUS=8,
    SPECTRA_SP5500=21,
    SPECTRA_SP6000=22,
    SPECTRA_SP7000=23,
    SPECTRA_SP4000=26,
    SPECTRA_SP65=27,
    SPECTRA_SP550_PLUS=28,
    SPECTRA_SP6000_PLUS=29,
    SPECTRA_SP7000_PLUS=30,
    MAGELLAN_MG5000=64,
    MAGELLAN_MG5050=65,
    MAGELLAN_MG5075=66,
    MAGELLAN_MG5050_PLUS=67,
)

FamilyIdEnum = Enum(
    Int8ub,
)

SerialPrefixToPanelType = Enum(
    Int8ub,
    DIGIPLEX_EVO_48=0x03,
    DIGIPLEX_EVO_96=0x04,
    DIGIPLEX_EVO_192=0x05,
    DIGIPLEX_EVO_HD=0x07,
    SPECTRA_SP4000=0x31,
    MAGELLAN_MG5000=0x20,
    MAGELLAN_MG5050=0x21,
    SPECTRA_SP5500=0x28,
    SPECTRA_SP6000=0x29,
    SPECTRA_SP65=0x45,
    SPECTRA_SP7000=0x2A,
    SPECTRA_UNIFIED=0x06,
)

CommunicationSourceIDEnum = Enum(
    Int8ub,
    NonValid_Source=0,
    Winload_Direct=1,
    Winload_IP=2,
    Winload_GSM=3,
    Winload_Dialer=4,
    NeWare_Direct=5,
    NeWare_IP=6,
    NeWare_GSM=7,
    NeWare_Dialer=8,
    IP_Direct=9,
    VDMP3_Direct=10,
    VDMP3_GSM=11,
)
