from construct import (
    Adapter,
    Array,
    Checksum,
    Container,
    Default,
    Enum,
    ExprAdapter,
    Flag,
    Int8ub,
    ListContainer,
    Rebuild,
    this,
)


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
    MAGELLAN_MG6250=100,
)

FamilyIdEnum = Enum(
    Int8ub,
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


class DictArray(Adapter):
    def __init__(self, count, first_index, subcon, pick_key: str = None):
        super().__init__(Array(count, subcon))
        self._first_index = first_index
        self._pick_key = pick_key

    def _decode(self, obj, context, path):
        if not isinstance(obj, list):
            raise TypeError("list should be passed for decoding")

        n_obj = Container()
        for item in obj:
            v = item
            if self._pick_key:
                v = item.get(self._pick_key)
            n_obj[item._index] = v

        return n_obj

    def _encode(self, obj, context, path):
        if not isinstance(obj, dict):
            raise TypeError("dict should be passed for decoding")

        n_obj = ListContainer()

        count = self.subcon.count  # Array count

        for k in range(self._first_index, self._first_index + count):
            o = {"_index": k}
            v = obj.get(k)
            if v is not None:
                if self._pick_key:
                    v = {self._pick_key: v}
                o.update(v)
            n_obj.append(o)

        return n_obj


class FlagsDict(Adapter):
    """Array of flags exposed as {index: bool}, indexes start from `first_index`"""

    def __init__(self, count, first_index=1):
        super().__init__(Array(count, Default(Flag, False)))
        self._indexes = range(first_index, first_index + count)

    def _decode(self, obj, context, path):
        return Container(zip(self._indexes, obj))

    def _encode(self, obj, context, path):
        if not isinstance(obj, dict):
            raise TypeError("dict should be passed for encoding")

        return [obj.get(k) for k in self._indexes]


def StatusFlags(count, start_index_from=1):
    return FlagsDict(count, start_index_from)
