"""
PRT3 state adapter — pure normalization layer.

Converts PRT3 protocol message types into the nested dict structures that
PAI's MemoryStorage and status_update pipeline expect.  No I/O, no asyncio,
no PAI runtime imports beyond the parser dataclasses and sanitize_key.

This module is the clean boundary between the PRT3 wire protocol and PAI's
internal state model.  All mapping decisions live here; panel.py calls
these functions and forwards results to the runtime.

Mapping decisions
-----------------

arm_state → PAI partition flags
  disarmed      → arm=False  arm_stay=False  arm_away=False  arm_force=False
  armed_away    → arm=True   arm_stay=False  arm_away=True   arm_force=False
  armed_force   → arm=True   arm_stay=False  arm_away=True   arm_force=True
                  (forced arm is always an away-mode arm)
  armed_stay    → arm=True   arm_stay=True   arm_away=False  arm_force=False
  armed_instant → arm=True   arm_stay=True   arm_away=False  arm_force=False
                  (instant arm = stay without entry delay; PAI has no separate
                   'instant' flag — it is represented as stay)

not_ready → ready_status (polarity inversion)
  PRT3 not_ready=True  → PAI ready_status=False

alarm → audible_alarm
  PRT3's area-level 'alarm' flag signals that the siren is active.  The
  nearest PAI equivalent is 'audible_alarm'; it is consumed by
  _update_partition_states() which derives current_state='triggered'.

zone open_state → open, tamper, fire_loop_trouble
  closed             → open=False  tamper=False  fire_loop_trouble=False
  open               → open=True   tamper=False  fire_loop_trouble=False
  tampered           → open=True   tamper=True   fire_loop_trouble=False
                       (tampered zone is also flagged open; PAI convention)
  fire_loop_trouble  → open=False  tamper=False  fire_loop_trouble=True

label element_type → PAI container name
  "zone" → "zone"
  "area" → "partition"    (PRT3 calls them 'areas'; PAI calls them 'partitions')
  "user" → "user"
"""

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

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
from paradox.lib.utils import sanitize_key

# ---------------------------------------------------------------------------
# Area (partition) status normalization
# ---------------------------------------------------------------------------

# arm_state → (arm, arm_stay, arm_away, arm_force)
_ARM_STATE_FLAGS: Dict[str, Tuple[bool, bool, bool, bool]] = {
    ARM_DISARMED: (False, False, False, False),
    ARM_AWAY:     (True,  False, True,  False),
    ARM_FORCE:    (True,  False, True,  True),   # forced arm is an away arm
    ARM_STAY:     (True,  True,  False, False),
    ARM_INSTANT:  (True,  True,  False, False),  # no PAI 'instant' flag; maps to stay
}


def partition_status_from_area(msg: PRT3AreaStatus) -> dict:
    """
    Map a PRT3AreaStatus to a PAI partition property dict.

    All keys match PAI's property_map and the format expected by
    MemoryStorage.update_container_object().
    """
    arm, arm_stay, arm_away, arm_force = _ARM_STATE_FLAGS[msg.arm_state]
    return {
        "arm":              arm,
        "arm_stay":         arm_stay,
        "arm_away":         arm_away,
        "arm_force":        arm_force,
        "trouble":          msg.trouble,
        "ready_status":     not msg.not_ready,   # PRT3 says 'not_ready'; PAI says 'ready'
        "audible_alarm":    msg.alarm,            # area alarm flag → siren active
        "strobe_alarm":     msg.strobe,
        "alarms_in_memory": msg.zone_in_memory,
    }


# ---------------------------------------------------------------------------
# Zone status normalization
# ---------------------------------------------------------------------------

def zone_status_from_zone(msg: PRT3ZoneStatus) -> dict:
    """
    Map a PRT3ZoneStatus to a PAI zone property dict.

    All keys match PAI's property_map and the format expected by
    MemoryStorage.update_container_object().
    """
    open_state = msg.open_state
    return {
        "open":                open_state in (ZONE_OPEN, ZONE_TAMPERED),
        "tamper":              open_state == ZONE_TAMPERED,
        "fire_loop_trouble":   open_state == ZONE_FIRE_LOOP_TROUBLE,
        "alarm":               msg.alarm,
        "fire":                msg.fire_alarm,
        "supervision_trouble": msg.supervision_trouble,
        "low_battery_trouble": msg.low_battery,
    }


# ---------------------------------------------------------------------------
# Label normalization
# ---------------------------------------------------------------------------

# PRT3 "area" → PAI container "partition"
_ELEMENT_TYPE_TO_CONTAINER: Dict[str, str] = {
    "zone": "zone",
    "area": "partition",
    "user": "user",
}


def label_entry_from_reply(msg: PRT3LabelReply) -> Tuple[str, int, dict]:
    """
    Convert a PRT3LabelReply to a (container_name, index, entry_dict) tuple.

    The entry_dict is compatible with MemoryStorage.deep_merge():
      {"id": n, "key": sanitized_label, "label": raw_label_stripped}

    Trailing spaces are stripped from the label (PRT3 pads to 16 chars with
    spaces; PAI displays labels without trailing whitespace).

    If the label is blank (all spaces), the key falls back to
    ``{container}_{index:03d}`` so the element still gets a usable key.
    """
    container = _ELEMENT_TYPE_TO_CONTAINER[msg.element_type]
    label = msg.label.rstrip()
    key = sanitize_key(label) if label else f"{container}_{msg.index:03d}"
    return container, msg.index, {"id": msg.index, "key": key, "label": label}


def labels_dict_from_replies(replies: Iterable[PRT3LabelReply]) -> dict:
    """
    Aggregate PRT3LabelReply messages into the format Paradox._on_labels_load()
    expects::

        {
          "zone":      {1: {"id": 1, "key": "front_door", "label": "Front Door"}, ...},
          "partition": {1: {"id": 1, "key": "home",       "label": "Home"},       ...},
          "user":      {1: {"id": 1, "key": "master",     "label": "Master"},     ...},
        }

    Duplicate indices for the same container are overwritten by the last
    reply seen; the panel should not send duplicates, but be defensive.
    """
    data: Dict[str, Dict[int, dict]] = defaultdict(dict)
    for msg in replies:
        container, idx, entry = label_entry_from_reply(msg)
        data[container][idx] = entry
    return dict(data)


# ---------------------------------------------------------------------------
# Flat status dict (convert_raw_status() compatible format)
# ---------------------------------------------------------------------------

def build_flat_status(
    area_msgs: Iterable[PRT3AreaStatus],
    zone_msgs: Iterable[PRT3ZoneStatus],
) -> dict:
    """
    Build the flat status dict compatible with convert_raw_status().

    Accumulates multiple area and zone status messages into::

        {
            "partition_arm":              {1: True, 2: False},
            "partition_arm_stay":         {1: False, 2: False},
            "partition_arm_away":         {1: True,  2: False},
            "partition_arm_force":        {1: False, 2: False},
            "partition_trouble":          {1: False, 2: False},
            "partition_ready_status":     {1: True,  2: True},
            "partition_audible_alarm":    {1: False, 2: False},
            "partition_strobe_alarm":     {1: False, 2: False},
            "partition_alarms_in_memory": {1: False, 2: False},
            "zone_open":                  {1: False, 2: True},
            "zone_tamper":                {1: False, 2: False},
            "zone_fire_loop_trouble":     {1: False, 2: False},
            "zone_alarm":                 {1: False, 2: False},
            "zone_fire":                  {1: False, 2: False},
            "zone_supervision_trouble":   {1: False, 2: False},
            "zone_low_battery_trouble":   {1: False, 2: False},
        }

    convert_raw_status() splits "partition_arm" on the first underscore to
    produce container="partition", prop="arm".  Multi-word properties like
    "arm_stay" or "low_battery_trouble" are split once to keep the container
    type and the rest becomes the property name.
    """
    p_by_prop: Dict[str, Dict[int, bool]] = {}
    z_by_prop: Dict[str, Dict[int, bool]] = {}

    for msg in area_msgs:
        props = partition_status_from_area(msg)
        for prop, val in props.items():
            p_by_prop.setdefault(prop, {})[msg.area] = val

    for msg in zone_msgs:
        props = zone_status_from_zone(msg)
        for prop, val in props.items():
            z_by_prop.setdefault(prop, {})[msg.zone] = val

    flat: dict = {}
    for prop, by_id in p_by_prop.items():
        flat[f"partition_{prop}"] = by_id
    for prop, by_id in z_by_prop.items():
        flat[f"zone_{prop}"] = by_id
    return flat
