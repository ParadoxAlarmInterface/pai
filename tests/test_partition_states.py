import pytest

from paradox.config import Config, config as cfg
from paradox.paradox import Paradox


@pytest.fixture
def alarm(monkeypatch, mocker):
    monkeypatch.setattr(
        cfg,
        "HOMEASSISTANT_ARM_NO_ENTRY_STATE",
        Config().HOMEASSISTANT_ARM_NO_ENTRY_STATE,
    )
    mocker.patch("paradox.lib.ps.sendChange")
    return Paradox()


def update_partition(alarm, flags):
    alarm.storage.get_container("partition").deep_merge(
        {"area_1": {"key": "area_1", **flags}}
    )
    alarm._update_partition_states()
    return alarm.storage.get_container("partition")["area_1"]


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, "disarmed"),
        ({"arm_no_entry": True}, "disarmed"),
        ({"arm": False, "arm_sleep": True, "arm_no_entry": True}, "disarmed"),
        ({"arm": True}, "armed_away"),
        ({"arm": True, "arm_away": True}, "armed_away"),
        ({"arm": True, "arm_no_entry": True}, "armed_night"),
        ({"arm": True, "arm_no_entry": True, "arm_away": True}, "armed_night"),
        ({"arm": True, "arm_stay": True}, "armed_home"),
        ({"arm": True, "arm_stay": True, "arm_no_entry": True}, "armed_home"),
        ({"arm": True, "arm_sleep": True}, "armed_night"),
        ({"arm": True, "arm_sleep": True, "arm_no_entry": True}, "armed_night"),
        (
            {
                "arm": True,
                "arm_stay": True,
                "arm_sleep": True,
                "arm_no_entry": True,
                "arm_away": True,
            },
            "armed_home",
        ),
    ],
)
def test_default_partition_states(alarm, flags, expected):
    partition = update_partition(alarm, flags)
    assert partition["current_state"] == expected
    assert partition["target_state"] == expected


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
@pytest.mark.parametrize("arm_away", [False, True])
def test_custom_no_entry_state(alarm, monkeypatch, state, arm_away):
    monkeypatch.setattr(cfg, "HOMEASSISTANT_ARM_NO_ENTRY_STATE", state)
    partition = update_partition(
        alarm, {"arm": True, "arm_no_entry": True, "arm_away": arm_away}
    )
    assert partition["current_state"] == state
    assert partition["target_state"] == state


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({"arm": False, "arm_no_entry": True}, "disarmed"),
        ({"arm": True}, "armed_away"),
        ({"arm": True, "arm_away": True}, "armed_away"),
        ({"arm": True, "arm_stay": True}, "armed_home"),
        ({"arm": True, "arm_stay": True, "arm_no_entry": True}, "armed_home"),
        ({"arm": True, "arm_sleep": True}, "armed_night"),
        ({"arm": True, "arm_sleep": True, "arm_no_entry": True}, "armed_night"),
        (
            {"arm": True, "arm_sleep": True, "arm_no_entry": True, "arm_away": True},
            "armed_night",
        ),
        (
            {
                "arm": True,
                "arm_stay": True,
                "arm_sleep": True,
                "arm_no_entry": True,
                "arm_away": True,
            },
            "armed_home",
        ),
    ],
)
def test_custom_mapping_preserves_other_modes(alarm, monkeypatch, flags, expected):
    monkeypatch.setattr(cfg, "HOMEASSISTANT_ARM_NO_ENTRY_STATE", "armed_custom_bypass")
    partition = update_partition(alarm, flags)
    assert partition["current_state"] == expected
    assert partition["target_state"] == expected


@pytest.mark.parametrize(
    "delays, expected",
    [
        ({"exit_delay": True}, "arming"),
        ({"entry_delay": True}, "pending"),
        ({"exit_delay": True, "entry_delay": True}, "arming"),
    ],
)
def test_delays_override_custom_current_state(alarm, monkeypatch, delays, expected):
    monkeypatch.setattr(cfg, "HOMEASSISTANT_ARM_NO_ENTRY_STATE", "armed_custom_bypass")
    partition = update_partition(alarm, {"arm": True, "arm_no_entry": True, **delays})
    assert partition["current_state"] == expected
    assert partition["target_state"] == "armed_custom_bypass"


@pytest.mark.parametrize(
    "alarm_flag", ["fire_alarm", "audible_alarm", "silent_alarm", "panic_alarm"]
)
@pytest.mark.parametrize("armed", [False, True])
def test_alarm_overrides_no_entry_and_both_delays(
    alarm, monkeypatch, alarm_flag, armed
):
    monkeypatch.setattr(cfg, "HOMEASSISTANT_ARM_NO_ENTRY_STATE", "armed_custom_bypass")
    alarm.storage.get_container("partition").deep_merge(
        {"area_1": {"key": "area_1", "target_state": "armed_home"}}
    )
    partition = update_partition(
        alarm,
        {
            "arm": armed,
            "arm_no_entry": True,
            "exit_delay": True,
            "entry_delay": True,
            alarm_flag: True,
        },
    )
    assert partition["current_state"] == "triggered"
    # The existing alarm branch leaves target_state untouched.
    assert partition["target_state"] == "armed_home"


def test_no_entry_state_tracks_flag_changes(alarm, monkeypatch):
    monkeypatch.setattr(cfg, "HOMEASSISTANT_ARM_NO_ENTRY_STATE", "armed_custom_bypass")
    partition = update_partition(alarm, {"arm": True, "arm_no_entry": True})
    assert partition["current_state"] == "armed_custom_bypass"

    partition = update_partition(alarm, {"arm_no_entry": False})
    assert partition["current_state"] == partition["target_state"] == "armed_away"

    partition = update_partition(alarm, {"arm": False, "arm_no_entry": True})
    assert partition["current_state"] == partition["target_state"] == "disarmed"
