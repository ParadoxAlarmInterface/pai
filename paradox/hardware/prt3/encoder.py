"""
PRT3 ASCII command encoder.

Pure functions — no side effects, no I/O.  Each function returns a bytes
object ready to write to the serial port (already \\r-terminated).

Command reference (PRT3 ASCII Programming Guide):

  Arm          AA{nn}{mode}{code}\\r   mode: A=away F=force S=stay I=instant
  Quick arm    AQ{nn}{mode}\\r         requires One-Touch Arming enabled on panel
  Disarm       AD{nn}{code}\\r
  Panic emerg  PE{nn}\\r
  Panic medic  PM{nn}\\r
  Panic fire   PF{nn}\\r
  Utility key  UK{nnn}\\r
  Area status  RA{nnn}\\r
  Zone status  RZ{nnn}\\r
  Area label   AL{nnn}\\r
  Zone label   ZL{nnn}\\r
  User label   UL{nnn}\\r

TODO (Phase 2): Implement each encoder.
"""

# ---------------------------------------------------------------------------
# Arm / disarm
# ---------------------------------------------------------------------------

def encode_arm(area: int, mode: str, code: str) -> bytes:
    """
    Build an AA (arm) command.

    :param area: 1-based area number (01-08 for EVO)
    :param mode: one of 'A' (away), 'F' (force), 'S' (stay), 'I' (instant)
    :param code: numeric user code as a string, e.g. '1234'

    TODO (Phase 2): Implement — return f'AA{area:02d}{mode}{code}\\r'.encode()
    """
    raise NotImplementedError("encode_arm() not yet implemented — see Phase 2")


def encode_quick_arm(area: int, mode: str) -> bytes:
    """
    Build an AQ (quick arm) command.

    Requires 'One-Touch Arming' enabled on the panel; silently ignored otherwise.

    TODO (Phase 2): Implement — return f'AQ{area:02d}{mode}\\r'.encode()
    """
    raise NotImplementedError("encode_quick_arm() not yet implemented — see Phase 2")


def encode_disarm(area: int, code: str) -> bytes:
    """
    Build an AD (disarm) command.

    TODO (Phase 2): Implement — return f'AD{area:02d}{code}\\r'.encode()
    """
    raise NotImplementedError("encode_disarm() not yet implemented — see Phase 2")


# ---------------------------------------------------------------------------
# Panic
# ---------------------------------------------------------------------------

def encode_panic_emergency(area: int) -> bytes:
    """PE — emergency panic.  TODO (Phase 2)."""
    raise NotImplementedError("encode_panic_emergency() not yet implemented — see Phase 2")


def encode_panic_medical(area: int) -> bytes:
    """PM — medical panic.  TODO (Phase 2)."""
    raise NotImplementedError("encode_panic_medical() not yet implemented — see Phase 2")


def encode_panic_fire(area: int) -> bytes:
    """PF — fire panic.  TODO (Phase 2)."""
    raise NotImplementedError("encode_panic_fire() not yet implemented — see Phase 2")


# ---------------------------------------------------------------------------
# Utility key
# ---------------------------------------------------------------------------

def encode_utility_key(key: int) -> bytes:
    """
    UK{nnn} — send utility key.

    TODO (Phase 2): Implement — return f'UK{key:03d}\\r'.encode()
    """
    raise NotImplementedError("encode_utility_key() not yet implemented — see Phase 2")


# ---------------------------------------------------------------------------
# Status / label requests
# ---------------------------------------------------------------------------

def encode_area_status_request(area: int) -> bytes:
    """RA{nnn}\\r — request area status.  TODO (Phase 2)."""
    raise NotImplementedError(
        "encode_area_status_request() not yet implemented — see Phase 2"
    )


def encode_zone_status_request(zone: int) -> bytes:
    """RZ{nnn}\\r — request zone status.  TODO (Phase 2)."""
    raise NotImplementedError(
        "encode_zone_status_request() not yet implemented — see Phase 2"
    )


def encode_area_label_request(area: int) -> bytes:
    """AL{nnn}\\r — request area label.  TODO (Phase 2)."""
    raise NotImplementedError(
        "encode_area_label_request() not yet implemented — see Phase 2"
    )


def encode_zone_label_request(zone: int) -> bytes:
    """ZL{nnn}\\r — request zone label.  TODO (Phase 2)."""
    raise NotImplementedError(
        "encode_zone_label_request() not yet implemented — see Phase 2"
    )


def encode_user_label_request(user: int) -> bytes:
    """UL{nnn}\\r — request user label.  TODO (Phase 2)."""
    raise NotImplementedError(
        "encode_user_label_request() not yet implemented — see Phase 2"
    )
