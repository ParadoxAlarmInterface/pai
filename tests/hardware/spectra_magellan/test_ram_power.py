"""
Tests for system power parsing on Spectra Plus panels (issue #366).

SP7000+ leaves the page 0 power bytes zeroed and reports voltages at the end
of RAM page 5 as little-endian millivolts:
  Offset  Size  Field
  26      2     vdc
  28      2     dc
  30      2     battery
"""

from paradox.hardware.spectra_magellan.parsers import (
    RAMDataParserMap,
    RAMDataParserMapPlus,
)
from paradox.lib.utils import deep_merge

# RAM pages captured from an SP7000+ v1.24; BabyWare showed AC 16.0 V, battery 13.6 V
SP7000_PLUS_PAGE0 = bytes.fromhex(
    "0000000000141a0a15162c000000000000000000000000000000000000000000"
)
SP7000_PLUS_PAGE5 = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000803eb1353035"
)


def test_plus_page5_power():
    data = RAMDataParserMapPlus[5].parse(SP7000_PLUS_PAGE5)

    assert data.system.power.vdc == 16.0
    assert data.system.power.dc == 13.7
    assert data.system.power.battery == 13.6


def test_plus_page5_overrides_zeroed_page0_power():
    pages = [
        RAMDataParserMapPlus[0].parse(SP7000_PLUS_PAGE0),
        RAMDataParserMapPlus[5].parse(SP7000_PLUS_PAGE5),
    ]

    # same merge as Paradox.loop
    merged = deep_merge(*pages, extend_lists=True, initializer={}, copy=False)

    assert merged["system"]["power"]["vdc"] == 16.0
    assert merged["system"]["power"]["dc"] == 13.7
    assert merged["system"]["power"]["battery"] == 13.6
    assert "time" in merged["system"]["date"]


def test_plus_map_only_overrides_page5():
    for address, parser in RAMDataParserMap.items():
        if address != 5:
            assert RAMDataParserMapPlus[address] is parser


def test_legacy_page5_has_no_power():
    data = RAMDataParserMap[5].parse(SP7000_PLUS_PAGE5)

    assert "system" not in data
