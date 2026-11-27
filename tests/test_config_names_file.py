"""``NAMES_FILE``: zone and partition display names from a YAML file."""

import pytest

from paradox.config import Config


@pytest.fixture(autouse=True)
def no_environment(monkeypatch):
    monkeypatch.delenv("PAI_NAMES_FILE", raising=False)
    monkeypatch.delenv("PAI_ZONE_NAMES", raising=False)
    monkeypatch.delenv("PAI_ZONE_DEVICE_CLASS", raising=False)
    monkeypatch.delenv("PAI_DIGIPLEX_PARTITION_NAMES", raising=False)


def load(monkeypatch, entries: dict) -> Config:
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: entries)
    c.load()
    return c


def write_names_file(tmp_path, content: str):
    path = tmp_path / "pai_names.yaml"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_no_names_file_keeps_defaults(monkeypatch):
    c = load(monkeypatch, {})

    assert c.NAMES_FILE == ""
    assert c.ZONE_NAMES == {}
    assert c.ZONE_DEVICE_CLASS == {}
    assert c.DIGIPLEX_PARTITION_NAMES == {}


def test_names_file_merges_zones_and_partitions(monkeypatch, tmp_path):
    path = write_names_file(
        tmp_path,
        """
zones:
  garazas:
    name: Garage
    area: garage
    device_class: motion
    open: Motion
    tamper: Tamper
  fasado_durys:
    name: Front door
    open: ""
partitions:
  1: House
  2: Garage
""",
    )

    c = load(monkeypatch, {"NAMES_FILE": path})

    assert c.ZONE_NAMES["garazas"] == {
        "name": "Garage",
        "area": "garage",
        "open": "Motion",
        "tamper": "Tamper",
    }
    assert c.ZONE_NAMES["fasado_durys"] == {"name": "Front door", "open": ""}
    assert c.ZONE_DEVICE_CLASS == {"garazas": "motion"}
    assert c.DIGIPLEX_PARTITION_NAMES == {1: "House", 2: "Garage"}


def test_names_file_overrides_options(monkeypatch, tmp_path):
    path = write_names_file(
        tmp_path,
        """
zones:
  garazas:
    name: Garage
partitions:
  1: House
""",
    )

    c = load(
        monkeypatch,
        {
            "NAMES_FILE": path,
            "ZONE_NAMES": {"garazas": {"name": "Old"}},
            "ZONE_DEVICE_CLASS": {"garazas": "door"},
            "DIGIPLEX_PARTITION_NAMES": {1: "Old"},
        },
    )

    assert c.ZONE_NAMES["garazas"] == {"name": "Garage"}
    assert c.ZONE_DEVICE_CLASS == {"garazas": "door"}
    assert c.DIGIPLEX_PARTITION_NAMES == {1: "House"}


def test_missing_names_file_is_not_fatal(monkeypatch, tmp_path, capsys):
    missing = str(tmp_path / "does-not-exist.yaml")

    c = load(monkeypatch, {"NAMES_FILE": missing})

    assert c.CONFIG_LOADED is True
    assert c.ZONE_NAMES == {}
    assert "NAMES_FILE not found" in capsys.readouterr().err


def test_invalid_names_file_is_not_fatal(monkeypatch, tmp_path, capsys):
    path = write_names_file(tmp_path, "- a\n- b\n")

    c = load(monkeypatch, {"NAMES_FILE": path})

    assert c.CONFIG_LOADED is True
    assert c.ZONE_NAMES == {}
    assert "must contain a mapping" in capsys.readouterr().err


def test_names_file_ignores_non_mapping_zone_entries(monkeypatch, tmp_path):
    path = write_names_file(
        tmp_path,
        """
zones:
  garazas:
    name: Garage
  broken: just a string
""",
    )

    c = load(monkeypatch, {"NAMES_FILE": path})

    assert c.ZONE_NAMES == {"garazas": {"name": "Garage"}}


def test_zone_types_option_populates_device_classes(monkeypatch):
    c = load(
        monkeypatch,
        {"ZONE_TYPES": ["fasado_durys=door", " gaisras = smoke "]},
    )

    assert c.ZONE_DEVICE_CLASS == {"fasado_durys": "door", "gaisras": "smoke"}


def test_zone_types_ignores_invalid_entries(monkeypatch, capsys):
    c = load(monkeypatch, {"ZONE_TYPES": ["nonsense", "=door", "key="]})

    assert c.ZONE_DEVICE_CLASS == {}
    assert "Ignoring ZONE_TYPES" in capsys.readouterr().err


def test_names_file_overrides_zone_types(monkeypatch, tmp_path):
    path = write_names_file(
        tmp_path,
        """
zones:
  fasado_durys:
    device_class: window
""",
    )

    c = load(monkeypatch, {"ZONE_TYPES": ["fasado_durys=door"], "NAMES_FILE": path})

    assert c.ZONE_DEVICE_CLASS == {"fasado_durys": "window"}


def test_names_file_system_names(monkeypatch, tmp_path):
    path = write_names_file(
        tmp_path,
        """
system:
  power_battery: baterijos įtampa
  pai_status: PAI būsena
""",
    )

    c = load(monkeypatch, {"NAMES_FILE": path})

    assert c.SYSTEM_NAMES == {
        "power_battery": "baterijos įtampa",
        "pai_status": "PAI būsena",
    }
