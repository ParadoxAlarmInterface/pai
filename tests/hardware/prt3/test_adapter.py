"""
Unit tests for the PRT3 state adapter (paradox.hardware.prt3.adapter).

Tests cover:
  - partition_status_from_area() — all arm states, all flag combinations
  - zone_status_from_zone() — all open_state values, all flag combinations
  - label_entry_from_reply() — area→partition mapping, key sanitization,
      trailing space stripping, blank label fallback
  - labels_dict_from_replies() — aggregation of mixed type replies
  - build_flat_status() — flat key format, multi-area/zone accumulation,
      empty inputs
"""

import pytest

from paradox.hardware.prt3.adapter import (
    build_flat_status,
    label_entry_from_reply,
    labels_dict_from_replies,
    partition_status_from_area,
    zone_status_from_zone,
)
from paradox.hardware.prt3.parser import (
    ARM_AWAY,
    ARM_DISARMED,
    ARM_FORCE,
    ARM_INSTANT,
    ARM_STAY,
    ZONE_CLOSED,
    ZONE_FIRE_LOOP_TROUBLE,
    ZONE_OPEN,
    ZONE_TAMPERED,
    PRT3AreaStatus,
    PRT3LabelReply,
    PRT3ZoneStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _area(area=1, arm_state=ARM_DISARMED, in_programming=False, trouble=False,
          not_ready=False, alarm=False, strobe=False, zone_in_memory=False):
    return PRT3AreaStatus(
        area=area,
        arm_state=arm_state,
        in_programming=in_programming,
        trouble=trouble,
        not_ready=not_ready,
        alarm=alarm,
        strobe=strobe,
        zone_in_memory=zone_in_memory,
    )


def _zone(zone=1, open_state=ZONE_CLOSED, alarm=False, fire_alarm=False,
          supervision_trouble=False, low_battery=False):
    return PRT3ZoneStatus(
        zone=zone,
        open_state=open_state,
        alarm=alarm,
        fire_alarm=fire_alarm,
        supervision_trouble=supervision_trouble,
        low_battery=low_battery,
    )


def _label(element_type="zone", index=1, label="Front Door  "):
    return PRT3LabelReply(element_type=element_type, index=index, label=label)


# ---------------------------------------------------------------------------
# partition_status_from_area
# ---------------------------------------------------------------------------


class TestPartitionStatusFromArea:

    # --- arm_state → boolean flag decomposition ---

    def test_disarmed(self):
        r = partition_status_from_area(_area(arm_state=ARM_DISARMED))
        assert r["arm"] is False
        assert r["arm_stay"] is False
        assert r["arm_away"] is False
        assert r["arm_force"] is False

    def test_armed_away(self):
        r = partition_status_from_area(_area(arm_state=ARM_AWAY))
        assert r["arm"] is True
        assert r["arm_stay"] is False
        assert r["arm_away"] is True
        assert r["arm_force"] is False

    def test_armed_force(self):
        r = partition_status_from_area(_area(arm_state=ARM_FORCE))
        assert r["arm"] is True
        assert r["arm_stay"] is False
        assert r["arm_away"] is True
        assert r["arm_force"] is True

    def test_armed_stay(self):
        r = partition_status_from_area(_area(arm_state=ARM_STAY))
        assert r["arm"] is True
        assert r["arm_stay"] is True
        assert r["arm_away"] is False
        assert r["arm_force"] is False

    def test_armed_instant_maps_to_stay(self):
        # PRT3 'instant' has no PAI equivalent; mapped to stay
        r = partition_status_from_area(_area(arm_state=ARM_INSTANT))
        assert r["arm"] is True
        assert r["arm_stay"] is True
        assert r["arm_away"] is False
        assert r["arm_force"] is False

    # --- individual flag mappings ---

    def test_trouble_true(self):
        r = partition_status_from_area(_area(trouble=True))
        assert r["trouble"] is True

    def test_trouble_false(self):
        r = partition_status_from_area(_area(trouble=False))
        assert r["trouble"] is False

    def test_not_ready_inverted_to_ready_status_false(self):
        r = partition_status_from_area(_area(not_ready=True))
        assert r["ready_status"] is False

    def test_ready_when_not_not_ready(self):
        r = partition_status_from_area(_area(not_ready=False))
        assert r["ready_status"] is True

    def test_alarm_maps_to_audible_alarm(self):
        r = partition_status_from_area(_area(alarm=True))
        assert r["audible_alarm"] is True

    def test_no_alarm(self):
        r = partition_status_from_area(_area(alarm=False))
        assert r["audible_alarm"] is False

    def test_strobe_maps_to_strobe_alarm(self):
        r = partition_status_from_area(_area(strobe=True))
        assert r["strobe_alarm"] is True

    def test_zone_in_memory_maps_to_alarms_in_memory(self):
        r = partition_status_from_area(_area(zone_in_memory=True))
        assert r["alarms_in_memory"] is True

    def test_all_flags_clear(self):
        r = partition_status_from_area(_area())
        assert r == {
            "arm": False,
            "arm_stay": False,
            "arm_away": False,
            "arm_force": False,
            "trouble": False,
            "ready_status": True,
            "audible_alarm": False,
            "strobe_alarm": False,
            "alarms_in_memory": False,
        }

    def test_all_flags_set(self):
        r = partition_status_from_area(_area(
            arm_state=ARM_AWAY,
            trouble=True,
            not_ready=True,
            alarm=True,
            strobe=True,
            zone_in_memory=True,
        ))
        assert r["arm"] is True
        assert r["arm_away"] is True
        assert r["trouble"] is True
        assert r["ready_status"] is False
        assert r["audible_alarm"] is True
        assert r["strobe_alarm"] is True
        assert r["alarms_in_memory"] is True

    def test_area_number_not_in_output(self):
        # area number is the container key, not a property in the dict
        r = partition_status_from_area(_area(area=5))
        assert "area" not in r

    def test_returns_nine_keys(self):
        r = partition_status_from_area(_area())
        assert len(r) == 9


# ---------------------------------------------------------------------------
# zone_status_from_zone
# ---------------------------------------------------------------------------


class TestZoneStatusFromZone:

    # --- open_state decomposition ---

    def test_closed_all_false(self):
        r = zone_status_from_zone(_zone(open_state=ZONE_CLOSED))
        assert r["open"] is False
        assert r["tamper"] is False
        assert r["fire_loop_trouble"] is False

    def test_open_sets_open_only(self):
        r = zone_status_from_zone(_zone(open_state=ZONE_OPEN))
        assert r["open"] is True
        assert r["tamper"] is False
        assert r["fire_loop_trouble"] is False

    def test_tampered_sets_open_and_tamper(self):
        r = zone_status_from_zone(_zone(open_state=ZONE_TAMPERED))
        assert r["open"] is True
        assert r["tamper"] is True
        assert r["fire_loop_trouble"] is False

    def test_fire_loop_trouble_sets_fire_loop_only(self):
        r = zone_status_from_zone(_zone(open_state=ZONE_FIRE_LOOP_TROUBLE))
        assert r["open"] is False
        assert r["tamper"] is False
        assert r["fire_loop_trouble"] is True

    # --- individual zone flag mappings ---

    def test_alarm_flag(self):
        r = zone_status_from_zone(_zone(alarm=True))
        assert r["alarm"] is True

    def test_fire_alarm_maps_to_fire(self):
        r = zone_status_from_zone(_zone(fire_alarm=True))
        assert r["fire"] is True

    def test_supervision_trouble(self):
        r = zone_status_from_zone(_zone(supervision_trouble=True))
        assert r["supervision_trouble"] is True

    def test_low_battery_maps_to_low_battery_trouble(self):
        r = zone_status_from_zone(_zone(low_battery=True))
        assert r["low_battery_trouble"] is True

    def test_all_flags_clear(self):
        r = zone_status_from_zone(_zone())
        assert r == {
            "open": False,
            "tamper": False,
            "fire_loop_trouble": False,
            "alarm": False,
            "fire": False,
            "supervision_trouble": False,
            "low_battery_trouble": False,
        }

    def test_all_flags_set(self):
        r = zone_status_from_zone(_zone(
            open_state=ZONE_TAMPERED,
            alarm=True, fire_alarm=True,
            supervision_trouble=True, low_battery=True,
        ))
        assert r["open"] is True
        assert r["tamper"] is True
        assert r["alarm"] is True
        assert r["fire"] is True
        assert r["supervision_trouble"] is True
        assert r["low_battery_trouble"] is True

    def test_returns_seven_keys(self):
        assert len(zone_status_from_zone(_zone())) == 7

    def test_zone_number_not_in_output(self):
        r = zone_status_from_zone(_zone(zone=7))
        assert "zone" not in r


# ---------------------------------------------------------------------------
# label_entry_from_reply
# ---------------------------------------------------------------------------


class TestLabelEntryFromReply:

    def test_zone_stays_zone(self):
        container, idx, entry = label_entry_from_reply(
            _label(element_type="zone", index=1, label="Front Door  ")
        )
        assert container == "zone"

    def test_area_maps_to_partition(self):
        container, idx, entry = label_entry_from_reply(
            _label(element_type="area", index=1, label="Home        ")
        )
        assert container == "partition"

    def test_user_stays_user(self):
        container, idx, entry = label_entry_from_reply(
            _label(element_type="user", index=1, label="Master      ")
        )
        assert container == "user"

    def test_index_preserved(self):
        _, idx, _ = label_entry_from_reply(_label(index=42))
        assert idx == 42

    def test_entry_has_id_key_label(self):
        _, _, entry = label_entry_from_reply(_label(index=3, label="Back Door   "))
        assert entry["id"] == 3
        assert "key" in entry
        assert "label" in entry

    def test_trailing_spaces_stripped_from_label(self):
        _, _, entry = label_entry_from_reply(_label(label="Front Door  "))
        assert entry["label"] == "Front Door"

    def test_key_is_sanitized(self):
        _, _, entry = label_entry_from_reply(_label(label="Front Door  "))
        # sanitize_key converts spaces/special chars to underscores
        assert " " not in entry["key"]

    def test_key_matches_label_content(self):
        _, _, entry = label_entry_from_reply(_label(label="Front Door  "))
        assert "Front" in entry["key"] or "front" in entry["key"].lower()

    def test_blank_label_falls_back_to_numeric_key(self):
        _, _, entry = label_entry_from_reply(
            PRT3LabelReply(element_type="zone", index=7, label="                ")
        )
        assert entry["label"] == ""
        assert entry["key"] == "zone_007"

    def test_blank_area_label_uses_partition_prefix(self):
        _, _, entry = label_entry_from_reply(
            PRT3LabelReply(element_type="area", index=3, label="                ")
        )
        assert entry["key"] == "partition_003"

    def test_max_zone_192(self):
        container, idx, entry = label_entry_from_reply(
            PRT3LabelReply(element_type="zone", index=192, label="Zone 192        ")
        )
        assert container == "zone"
        assert idx == 192
        assert entry["id"] == 192

    def test_max_user_999(self):
        container, idx, entry = label_entry_from_reply(
            PRT3LabelReply(element_type="user", index=999, label="User 999        ")
        )
        assert idx == 999


# ---------------------------------------------------------------------------
# labels_dict_from_replies
# ---------------------------------------------------------------------------


class TestLabelsDictFromReplies:

    def test_empty_input(self):
        result = labels_dict_from_replies([])
        assert result == {}

    def test_single_zone_label(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="zone", index=1, label="Front Door      ")
        ])
        assert "zone" in result
        assert 1 in result["zone"]
        assert result["zone"][1]["label"] == "Front Door"

    def test_area_label_under_partition_key(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="area", index=1, label="Home            ")
        ])
        assert "partition" in result
        assert 1 in result["partition"]

    def test_mixed_types_each_in_own_container(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="zone",  index=1, label="Front Door      "),
            PRT3LabelReply(element_type="area",  index=1, label="Home            "),
            PRT3LabelReply(element_type="user",  index=1, label="Master          "),
        ])
        assert "zone" in result
        assert "partition" in result
        assert "user" in result

    def test_multiple_zones(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="zone", index=1, label="Front Door      "),
            PRT3LabelReply(element_type="zone", index=2, label="Back Door       "),
        ])
        assert len(result["zone"]) == 2
        assert result["zone"][2]["label"] == "Back Door"

    def test_duplicate_index_overwritten_by_last(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="zone", index=1, label="First Label     "),
            PRT3LabelReply(element_type="zone", index=1, label="Second Label    "),
        ])
        assert result["zone"][1]["label"] == "Second Label"

    def test_entry_format_correct(self):
        result = labels_dict_from_replies([
            PRT3LabelReply(element_type="zone", index=5, label="Garage Door     ")
        ])
        entry = result["zone"][5]
        assert entry["id"] == 5
        assert entry["key"] != ""
        assert entry["label"] == "Garage Door"


# ---------------------------------------------------------------------------
# build_flat_status
# ---------------------------------------------------------------------------


class TestBuildFlatStatus:

    def test_empty_inputs(self):
        result = build_flat_status([], [])
        assert result == {}

    def test_single_disarmed_area(self):
        result = build_flat_status([_area(area=1, arm_state=ARM_DISARMED)], [])
        assert result["partition_arm"] == {1: False}
        assert result["partition_arm_stay"] == {1: False}
        assert result["partition_arm_away"] == {1: False}
        assert result["partition_ready_status"] == {1: True}

    def test_single_armed_away_area(self):
        result = build_flat_status([_area(area=1, arm_state=ARM_AWAY)], [])
        assert result["partition_arm"] == {1: True}
        assert result["partition_arm_away"] == {1: True}
        assert result["partition_arm_stay"] == {1: False}

    def test_multiple_areas_keyed_by_area_id(self):
        result = build_flat_status([
            _area(area=1, arm_state=ARM_AWAY),
            _area(area=2, arm_state=ARM_DISARMED),
        ], [])
        assert result["partition_arm"] == {1: True, 2: False}
        assert result["partition_arm_away"] == {1: True, 2: False}

    def test_single_closed_zone(self):
        result = build_flat_status([], [_zone(zone=1, open_state=ZONE_CLOSED)])
        assert result["zone_open"] == {1: False}
        assert result["zone_tamper"] == {1: False}
        assert result["zone_alarm"] == {1: False}

    def test_single_open_zone(self):
        result = build_flat_status([], [_zone(zone=2, open_state=ZONE_OPEN)])
        assert result["zone_open"] == {2: True}
        assert result["zone_tamper"] == {2: False}

    def test_tampered_zone_sets_open_and_tamper(self):
        result = build_flat_status([], [_zone(zone=3, open_state=ZONE_TAMPERED)])
        assert result["zone_open"] == {3: True}
        assert result["zone_tamper"] == {3: True}

    def test_multiple_zones_keyed_by_zone_id(self):
        result = build_flat_status([], [
            _zone(zone=1, open_state=ZONE_CLOSED),
            _zone(zone=5, open_state=ZONE_OPEN),
        ])
        assert result["zone_open"] == {1: False, 5: True}

    def test_partition_keys_prefixed_partition(self):
        result = build_flat_status([_area(area=1)], [])
        for key in result:
            assert key.startswith("partition_"), f"unexpected key: {key!r}"

    def test_zone_keys_prefixed_zone(self):
        result = build_flat_status([], [_zone(zone=1)])
        for key in result:
            assert key.startswith("zone_"), f"unexpected key: {key!r}"

    def test_mixed_areas_and_zones(self):
        result = build_flat_status(
            [_area(area=1, arm_state=ARM_STAY)],
            [_zone(zone=1, open_state=ZONE_OPEN, alarm=True)],
        )
        assert result["partition_arm_stay"] == {1: True}
        assert result["zone_open"] == {1: True}
        assert result["zone_alarm"] == {1: True}

    def test_ready_status_inversion_in_flat_dict(self):
        # not_ready=True on wire → ready_status=False in flat dict
        result = build_flat_status([_area(area=1, not_ready=True)], [])
        assert result["partition_ready_status"] == {1: False}

    def test_fire_alarm_zone_maps_to_zone_fire(self):
        result = build_flat_status([], [_zone(zone=1, fire_alarm=True)])
        assert result["zone_fire"] == {1: True}

    def test_alarm_area_maps_to_partition_audible_alarm(self):
        result = build_flat_status([_area(area=1, alarm=True)], [])
        assert result["partition_audible_alarm"] == {1: True}

    def test_low_battery_zone_maps_to_low_battery_trouble(self):
        result = build_flat_status([], [_zone(zone=1, low_battery=True)])
        assert result["zone_low_battery_trouble"] == {1: True}

    def test_supervision_trouble_zone(self):
        result = build_flat_status([], [_zone(zone=1, supervision_trouble=True)])
        assert result["zone_supervision_trouble"] == {1: True}

    def test_all_9_partition_props_present(self):
        result = build_flat_status([_area(area=1)], [])
        expected = {
            "partition_arm", "partition_arm_stay", "partition_arm_away",
            "partition_arm_force", "partition_trouble", "partition_ready_status",
            "partition_audible_alarm", "partition_strobe_alarm",
            "partition_alarms_in_memory",
        }
        assert expected.issubset(result.keys())

    def test_all_7_zone_props_present(self):
        result = build_flat_status([], [_zone(zone=1)])
        expected = {
            "zone_open", "zone_tamper", "zone_fire_loop_trouble",
            "zone_alarm", "zone_fire", "zone_supervision_trouble",
            "zone_low_battery_trouble",
        }
        assert expected.issubset(result.keys())
