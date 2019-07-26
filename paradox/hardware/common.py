from construct import *


def calculate_checksum(message):
    r = 0
    for c in message:
        r += c
    r = (r % 256)
    return bytes([r])

HexInt = ExprAdapter(Int8ub, lambda obj, path: int(hex(obj)[2:], 16), lambda obj, path: int(str(obj), 16))

ProductIdEnum = Enum(Int8ub,
                     DIGIPLEX_v13=0,
                     DIGIPLEX_v2=1,
                     DIGIPLEX_NE=2,
                     DIGIPLEX_EVO_48=3,
                     DIGIPLEX_EVO_96=4,
                     DIGIPLEX_EVO_192=5,
                     DIGIPLEX_EVO_HD=7,
                     SPECTRA_SP5500=21,
                     SPECTRA_SP6000=22,
                     SPECTRA_SP7000=23,
                     SPECTRA_SP4000=26,
                     SPECTRA_SP65=27,
                     MAGELLAN_MG5000=64,
                     MAGELLAN_MG5050=65
                     )

CommunicationSourceIDEnum = Enum(Int8ub,
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
                                 VDMP3_GSM=11
                                 )
