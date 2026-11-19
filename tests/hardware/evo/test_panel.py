from paradox.hardware import create_panel
from paradox.hardware.evo import Panel_EVO192, Panel_EVOHD, Panel_EVOHDPlus
from paradox.hardware.evo.parsers import RAMDataParserMap, RAMDataParserMap_EVOHDPlus
from paradox.hardware.parsers import StartCommunicationResponse


def create_evo192_panel(alarm=None, product_id=5):
    # all-zero payload, so the checksum equals the product id
    payload = bytes(4) + bytes([product_id]) + bytes(31) + bytes([product_id])
    data = StartCommunicationResponse.parse(payload)

    return create_panel(alarm, data)


def test_create_panel():
    panel = create_evo192_panel()

    assert isinstance(panel, Panel_EVO192)


def test_create_evohd_panels_use_own_ram_parsers():
    evohd = create_evo192_panel(product_id=7)
    evohd_plus = create_evo192_panel(product_id=8)

    assert type(evohd) is Panel_EVOHD
    assert evohd.ram_parser_map is RAMDataParserMap
    assert isinstance(evohd_plus, Panel_EVOHDPlus)
    assert evohd_plus.ram_parser_map is RAMDataParserMap_EVOHDPlus
