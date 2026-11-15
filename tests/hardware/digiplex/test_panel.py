"""Which Digiplex zones / partitions are published (load_labels + status)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from construct import Container
import pytest

from paradox.config import config as cfg
from paradox.data.memory_storage import MemoryStorage
from paradox.hardware.digiplex.panel import ZONE_LABELS_BASE, PanelDGP848


def _labels(names: dict) -> dict:
    """EEPROM label blocks (32 bytes = two zones) keyed by address."""
    raw = bytearray(48 * 16)
    for zone, name in names.items():
        raw[(zone - 1) * 16 : (zone - 1) * 16 + len(name)] = name
    return {
        ZONE_LABELS_BASE + offset: bytes(raw[offset : offset + 32])
        for offset in range(0, len(raw), 32)
    }


def _zone_status(open_zones=(), tamper_zones=()) -> bytes:
    def bits(zones):
        value = sum(1 << (zone - 1) for zone in zones)
        return value.to_bytes(6, "little")

    return bits(open_zones) + bits(tamper_zones)


def _panel(labels: dict) -> PanelDGP848:
    memory = _labels(labels)
    panel = PanelDGP848(MagicMock())
    panel._read_eeprom = AsyncMock(side_effect=lambda address, count: memory[address])
    return panel


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {})
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {})


async def test_all_zones_are_published_with_fallback_labels():
    zones = (await _panel({1: b"fasado\x00durys", 2: b"virtuve"}).load_labels())[
        "zone"
    ]

    assert sorted(zones) == list(range(1, 49))
    assert zones[1]["label"] == "fasado durys"
    assert zones[1]["key"] == "fasado_durys"
    assert zones[30]["label"] == "Zone 30"
    assert zones[30]["key"] == "zone_30"


async def test_labelled_zone_keeps_key_on_fallback_collision():
    zones = (await _panel({2: b"zone 1"}).load_labels())["zone"]

    assert zones[2]["key"] == "zone_1"
    assert zones[1]["key"] == "zone_1_1"
    assert zones[1]["label"] == "Zone 1"


async def test_labels_use_configured_encoding(monkeypatch):
    monkeypatch.setattr(cfg, "LABEL_ENCODING", "latin-1")

    zones = (await _panel({1: b"gar\xe1\xbeas"}).load_labels())["zone"]

    assert zones[1]["label"] == "gar\xe1\xbeas"


async def test_case_only_label_collision_gets_suffix(monkeypatch):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {"1": "House", "2": "house"})
    labels = await _panel({1: b"Kitchen", 2: b"kitchen"}).load_labels()

    assert [labels["zone"][i]["key"] for i in (1, 2)] == ["Kitchen", "kitchen_2"]
    assert [labels["partition"][i]["key"] for i in (1, 2)] == ["House", "house_2"]


async def test_configured_names_hide_unlabelled_and_unlisted_duplicates(monkeypatch):
    monkeypatch.setattr(
        cfg,
        "ZONE_NAMES",
        {"fasado_durys": {}, "garazo_vartai": {}},
    )
    zones = (
        await _panel(
            {1: b"fasado durys", 7: b"garazo vartai", 24: b"garazo vartai"}
        ).load_labels()
    )["zone"]

    assert sorted(zones) == [1, 7]
    assert zones[1]["key"] == "fasado_durys"
    assert zones[7]["key"] == "garazo_vartai"


@pytest.mark.parametrize(
    ("labels", "device_class", "open_published", "tamper_published"),
    [
        ({1: b"door"}, "door", True, False),
        ({1: b"window"}, "window", True, False),
        ({1: b"motion"}, "motion", True, True),
        ({1: b"tamper"}, "tamper", False, True),
    ],
)
async def test_properties_filtered_by_zone_type(
    monkeypatch, labels, device_class, open_published, tamper_published
):
    key = next(iter(labels.values())).decode()
    monkeypatch.setattr(cfg, "ZONE_NAMES", {key: {}})
    monkeypatch.setattr(cfg, "ZONE_DEVICE_CLASS", {key: device_class})
    panel = _panel(labels)
    await panel.load_labels()

    result = {"zone_open": {1: True}, "zone_tamper": {1: True}}
    panel._keep_published(result)

    assert bool(result["zone_open"]) is open_published
    assert bool(result["zone_tamper"]) is tamper_published


async def test_zone_limits_select_zones(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {"zone": "2,5"})
    panel = _panel({1: b"fasado durys", 2: b"virtuve"})

    zones = (await panel.load_labels())["zone"]

    assert sorted(zones) == [2, 5]
    assert zones[5]["label"] == "Zone 5"


async def test_tamper_is_kept_for_every_published_zone():
    panel = _panel({1: b"fasado durys", 2: b"virtuve"})
    await panel.load_labels()

    reply = Container(
        fields=Container(
            value=Container(
                address=0x8153,
                data=_zone_status(open_zones=[3], tamper_zones=[1, 2]) + bytes(20),
            )
        )
    )
    panel.core.send_wait = AsyncMock(return_value=reply)

    status = await panel.request_status(0x8153)

    assert status["zone_tamper"][1] is True
    assert status["zone_tamper"][2] is True
    assert status["zone_open"][3] is True
    assert status["zone_open"][1] is False


async def test_partition_names_only_supply_labels(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {"1": "House", 6: "Shed"})
    panel = _panel({})

    with caplog.at_level(logging.WARNING):
        partitions = (await panel.load_labels())["partition"]

    assert {i: p["label"] for i, p in partitions.items()} == {
        1: "House",
        2: "Partition 2",
    }
    assert "partition [6] not supported" in caplog.text


async def test_partition_limits_restrict_status(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {"partition": "2"})
    panel = _panel({})
    assert list((await panel.load_labels())["partition"]) == [2]

    data = bytearray(32)
    data[16] = data[21] = 0x01  # partitions 1 and 2 armed
    reply = Container(fields=Container(value=Container(address=0x8185, data=data)))
    panel.core.send_wait = AsyncMock(return_value=reply)

    status = await panel.request_status(0x8185)

    assert set(status["partition_status"]) == {2}
    assert status["partition_status"][2]["arm"] is True


def test_ne96_warns_about_unsupported_zones(caplog):
    response = Container(
        fields=Container(value=Container(product_id="DIGIPLEX_NE"), data=b"")
    )

    with caplog.at_level(logging.WARNING):
        PanelDGP848(MagicMock(), response)

    assert "only zones 1-48 and partitions 1-2 are supported" in caplog.text


async def test_fallback_key_never_duplicates_a_labelled_key():
    zones = (await _panel({2: b"zone 1", 3: b"zone 1 1"}).load_labels())["zone"]

    assert zones[2]["key"] == "zone_1"
    assert zones[3]["key"] == "zone_1_1"
    assert len({z["key"] for z in zones.values()}) == len(zones)


async def test_limits_do_not_change_labelled_keys(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {"zone": [2]})
    zones = (await _panel({1: b"Kitchen", 2: b"Kitchen"}).load_labels())["zone"]

    assert list(zones) == [2]
    assert zones[2]["key"] == "Kitchen_2"


async def test_suffixed_zone_keys_are_unique():
    zones = (
        await _panel({1: b"Kitchen 3", 2: b"Kitchen", 3: b"Kitchen"}).load_labels()
    )["zone"]

    assert zones[1]["key"] == "Kitchen_3"
    assert zones[2]["key"] == "Kitchen"
    assert zones[3]["key"] == "Kitchen_3_3"
    assert len({zone["key"] for zone in zones.values()}) == len(zones)


async def test_partition_keys_are_unique_before_limits(monkeypatch):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {"1": "House", "2": "House"})
    all_partitions = (await _panel({}).load_labels())["partition"]
    assert [p["key"] for p in all_partitions.values()] == ["House", "House_2"]

    monkeypatch.setattr(cfg, "LIMITS", {"partition": "2"})
    limited = (await _panel({}).load_labels())["partition"]
    assert limited[2]["key"] == "House_2"


async def test_partition_name_collision_with_default_is_unique(monkeypatch):
    monkeypatch.setattr(cfg, "DIGIPLEX_PARTITION_NAMES", {"1": "Partition 2"})

    partitions = (await _panel({}).load_labels())["partition"]

    assert partitions[1]["key"] == "Partition_2"
    assert partitions[2]["key"] == "Partition_2_2"


def test_empty_selection_publishes_nothing():
    panel = _panel({})
    result = {"zone_open": {1: True}, "partition_status": {1: {"arm": False}}}

    panel._keep_published(result)

    assert result == {"zone_open": {}, "partition_status": {}}


async def test_eeprom_timeout_returns_empty_block(caplog):
    panel = PanelDGP848(MagicMock())
    panel.core.send_wait = AsyncMock(side_effect=asyncio.TimeoutError)

    with caplog.at_level(logging.WARNING):
        assert await panel._read_eeprom(ZONE_LABELS_BASE, 32) == b""

    assert "EEPROM read at 0x2000 timed out" in caplog.text


@pytest.mark.parametrize("partitions", [[], [9], [1, 9]])
async def test_unsupported_partition_selection_is_rejected(partitions):
    panel = _panel({})
    panel.core.send_wait = AsyncMock()

    assert await panel.control_partitions(partitions, "arm") is False
    panel.core.send_wait.assert_not_awaited()


async def test_failed_label_read_keeps_published_labels():
    memory = _labels({1: b"fasado durys", 3: b"virtuve"})
    memory[ZONE_LABELS_BASE] = b""  # zones 1-2 time out on reconnect
    core = MagicMock()
    core.storage = MemoryStorage()
    core.storage.get_container("zone").deep_merge(
        {
            1: {"key": "fasado_durys", "label": "fasado durys"},
            2: {"key": "zone_2_2", "label": "Zone 2"},
        }
    )
    panel = PanelDGP848(core)
    panel._read_eeprom = AsyncMock(side_effect=lambda address, count: memory[address])

    zones = (await panel.load_labels())["zone"]

    assert zones[1]["key"] == "fasado_durys"
    assert (zones[2]["key"], zones[2]["label"]) == ("zone_2_2", "Zone 2")
    assert zones[3]["key"] == "virtuve"


async def test_partition_command_ignores_stale_echo():
    from paradox.hardware.digiplex import parsers

    panel = _panel({})
    panel.core.send_wait = AsyncMock(return_value=None)
    await panel.control_partitions([1], "disarm")
    accepts = panel.core.send_wait.await_args.kwargs["reply_expected"]

    def echo(partitions):
        frame = parsers.build_partition_action(partitions)
        return parsers.PerformPartitionAction.parse(frame)

    assert accepts(echo({1: 0x6}))
    assert not accepts(echo({1: 0x2}))  # late echo of an earlier "arm"
