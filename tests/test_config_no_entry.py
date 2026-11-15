import json

import pytest

from paradox.config import Config


@pytest.fixture(autouse=True)
def no_environment_override(monkeypatch):
    monkeypatch.delenv("PAI_HOMEASSISTANT_ARM_NO_ENTRY_STATE", raising=False)


def load_config(tmp_path, entries):
    path = tmp_path / "pai.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    config = Config()
    config.load(str(path))
    return config


def test_default_no_entry_state(tmp_path):
    assert load_config(tmp_path, {}).HOMEASSISTANT_ARM_NO_ENTRY_STATE == "armed_night"


@pytest.mark.parametrize(
    "state",
    [
        "armed_home",
        "armed_away",
        "armed_night",
        "armed_vacation",
        "armed_custom_bypass",
    ],
)
def test_allowed_no_entry_state(tmp_path, state):
    config = load_config(tmp_path, {"HOMEASSISTANT_ARM_NO_ENTRY_STATE": state})
    assert config.HOMEASSISTANT_ARM_NO_ENTRY_STATE == state


@pytest.mark.parametrize(
    "state",
    [
        "disarmed",
        "triggered",
        "arming",
        "pending",
        "disarming",
        "unavailable",
        "unknown",
        "armed_instant",
        "armed",
        "ARMED_AWAY",
        "",
        None,
        True,
        1,
        [],
        {},
    ],
)
def test_invalid_no_entry_state_rejected(tmp_path, state):
    with pytest.raises(Exception, match="HOMEASSISTANT_ARM_NO_ENTRY_STATE"):
        load_config(tmp_path, {"HOMEASSISTANT_ARM_NO_ENTRY_STATE": state})


def test_no_entry_state_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PAI_HOMEASSISTANT_ARM_NO_ENTRY_STATE", "armed_away")
    config = load_config(tmp_path, {"HOMEASSISTANT_ARM_NO_ENTRY_STATE": "armed_night"})
    assert config.HOMEASSISTANT_ARM_NO_ENTRY_STATE == "armed_away"


def test_invalid_no_entry_state_environment_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PAI_HOMEASSISTANT_ARM_NO_ENTRY_STATE", "disarmed")
    with pytest.raises(Exception, match="HOMEASSISTANT_ARM_NO_ENTRY_STATE"):
        load_config(tmp_path, {})
