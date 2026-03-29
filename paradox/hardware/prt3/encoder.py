"""
PRT3 ASCII command encoder.

Pure functions — no side effects, no I/O.  Each function returns a
``bytes`` object ready to write to the serial port, including the trailing
``\\r`` (ASCII 0x0D).

Command reference (PRT3 ASCII Programming Guide, v1 scope only):

  RA{nnn}\\r               Request area status  (nnn = 001-008)
  RZ{nnn}\\r               Request zone status  (nnn = 001-192)
  AL{nnn}\\r               Request area label   (nnn = 001-008)
  ZL{nnn}\\r               Request zone label   (nnn = 001-192)
  UL{nnn}\\r               Request user label   (nnn = 001-999)
  AA{nnn}{mode}{code}\\r   Arm area             (mode: A/F/S/I, code: 1-6 digits)
  AQ{nnn}{mode}\\r         Quick-arm area       (requires One-Touch Arming on panel)
  AD{nnn}{code}\\r         Disarm area          (code: 1-6 digits)
  PE{nnn}\\r               Emergency panic
  PM{nnn}\\r               Medical panic
  PF{nnn}\\r               Fire panic
  UK{nnn}\\r               Utility key          (nnn = 001-251)

All area numbers are 3-digit zero-padded (001-008) even though only 8 areas
exist.  Zone, user and key numbers are also 3-digit zero-padded.  This
matches the spec byte-table exactly.

Out-of-scope for v1 (documented but deliberately not implemented here):
  VO{nnn}\\r  / VC{nnn}\\r   Virtual input open / closed
  SR{nnn}\\r               Smoke reset
"""

# ---------------------------------------------------------------------------
# Arm-mode constants  (pass as the ``mode`` argument to encode_arm /
#                     encode_quick_arm)
# ---------------------------------------------------------------------------

ARM_MODE_AWAY    = "A"   # Regular arm (away)
ARM_MODE_FORCE   = "F"   # Force arm
ARM_MODE_STAY    = "S"   # Stay arm
ARM_MODE_INSTANT = "I"   # Instant arm

_VALID_ARM_MODES = frozenset({ARM_MODE_AWAY, ARM_MODE_FORCE, ARM_MODE_STAY, ARM_MODE_INSTANT})

# ---------------------------------------------------------------------------
# Limits directly from PRT3 ASCII Programming Guide / Panel Specifications
# ---------------------------------------------------------------------------

_AREA_MIN, _AREA_MAX   = 1, 8
_ZONE_MIN, _ZONE_MAX   = 1, 192
_USER_MIN, _USER_MAX   = 1, 999
_KEY_MIN,  _KEY_MAX    = 1, 251
_CODE_MIN_LEN          = 1   # spec: "enter only the appropriate amount of digits"
_CODE_MAX_LEN          = 6   # spec: "up to 6 digits"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_area(area: int) -> None:
    if not (_AREA_MIN <= area <= _AREA_MAX):
        raise ValueError(
            f"area must be {_AREA_MIN}-{_AREA_MAX}, got {area!r}"
        )


def _validate_zone(zone: int) -> None:
    if not (_ZONE_MIN <= zone <= _ZONE_MAX):
        raise ValueError(
            f"zone must be {_ZONE_MIN}-{_ZONE_MAX}, got {zone!r}"
        )


def _validate_user(user: int) -> None:
    if not (_USER_MIN <= user <= _USER_MAX):
        raise ValueError(
            f"user must be {_USER_MIN}-{_USER_MAX}, got {user!r}"
        )


def _validate_key(key: int) -> None:
    if not (_KEY_MIN <= key <= _KEY_MAX):
        raise ValueError(
            f"utility key must be {_KEY_MIN}-{_KEY_MAX}, got {key!r}"
        )


def _validate_arm_mode(mode: str) -> None:
    if mode not in _VALID_ARM_MODES:
        raise ValueError(
            f"arm mode must be one of {sorted(_VALID_ARM_MODES)}, got {mode!r}"
        )


def _validate_code(code: str) -> None:
    if not isinstance(code, str):
        raise TypeError(f"code must be a str, got {type(code).__name__!r}")
    if not code:
        raise ValueError("code must not be empty")
    if len(code) > _CODE_MAX_LEN:
        raise ValueError(
            f"code must be at most {_CODE_MAX_LEN} digits, got {len(code)!r}"
        )
    if not code.isdigit():
        raise ValueError(f"code must contain only digits, got {code!r}")


def _cmd(s: str) -> bytes:
    """Append ``\\r`` and encode as ASCII bytes."""
    return (s + "\r").encode("ascii")


# ---------------------------------------------------------------------------
# Status and label requests
# ---------------------------------------------------------------------------


def encode_area_status_request(area: int) -> bytes:
    """``RA{nnn}\\r`` — request area status.

    :param area: 1-based area number (1-8).
    :returns: ASCII bytes ready to write to the serial port.
    :raises ValueError: if *area* is out of range.
    """
    _validate_area(area)
    return _cmd(f"RA{area:03d}")


def encode_zone_status_request(zone: int) -> bytes:
    """``RZ{nnn}\\r`` — request zone status.

    :param zone: 1-based zone number (1-192).
    :raises ValueError: if *zone* is out of range.
    """
    _validate_zone(zone)
    return _cmd(f"RZ{zone:03d}")


def encode_area_label_request(area: int) -> bytes:
    """``AL{nnn}\\r`` — request area label.

    :param area: 1-based area number (1-8).
    :raises ValueError: if *area* is out of range.
    """
    _validate_area(area)
    return _cmd(f"AL{area:03d}")


def encode_zone_label_request(zone: int) -> bytes:
    """``ZL{nnn}\\r`` — request zone label.

    :param zone: 1-based zone number (1-192).
    :raises ValueError: if *zone* is out of range.
    """
    _validate_zone(zone)
    return _cmd(f"ZL{zone:03d}")


def encode_user_label_request(user: int) -> bytes:
    """``UL{nnn}\\r`` — request user label.

    :param user: 1-based user number (1-999).
    :raises ValueError: if *user* is out of range.
    """
    _validate_user(user)
    return _cmd(f"UL{user:03d}")


# ---------------------------------------------------------------------------
# Arm / quick arm / disarm
# ---------------------------------------------------------------------------


def encode_arm(area: int, mode: str, code: str) -> bytes:
    """``AA{nnn}{mode}{code}\\r`` — arm an area.

    :param area: 1-based area number (1-8).
    :param mode: one of ``ARM_MODE_AWAY`` ('A'), ``ARM_MODE_FORCE`` ('F'),
                 ``ARM_MODE_STAY`` ('S'), ``ARM_MODE_INSTANT`` ('I').
    :param code: user code string, 1-6 decimal digits.  Variable length —
                 do **not** pad to 6; the panel accepts the exact digits sent.
    :raises ValueError: if any argument is invalid.

    Note: the echo prefix is always the first 5 chars of the command
    (``AA{nnn}``), regardless of code length.
    """
    _validate_area(area)
    _validate_arm_mode(mode)
    _validate_code(code)
    return _cmd(f"AA{area:03d}{mode}{code}")


def encode_quick_arm(area: int, mode: str) -> bytes:
    """``AQ{nnn}{mode}\\r`` — quick-arm an area (no user code required).

    Requires **One-Touch Arming** to be enabled in the Digiplex panel
    programming.  If the feature is disabled the panel silently ignores the
    command (no &fail echo is returned).

    :param area: 1-based area number (1-8).
    :param mode: one of the ARM_MODE_* constants.
    :raises ValueError: if any argument is invalid.
    """
    _validate_area(area)
    _validate_arm_mode(mode)
    return _cmd(f"AQ{area:03d}{mode}")


def encode_disarm(area: int, code: str) -> bytes:
    """``AD{nnn}{code}\\r`` — disarm an area.

    :param area: 1-based area number (1-8).
    :param code: user code string, 1-6 decimal digits.
    :raises ValueError: if any argument is invalid.
    """
    _validate_area(area)
    _validate_code(code)
    return _cmd(f"AD{area:03d}{code}")


# ---------------------------------------------------------------------------
# Panic commands
# ---------------------------------------------------------------------------


def encode_panic_emergency(area: int) -> bytes:
    """``PE{nnn}\\r`` — trigger an emergency (police) panic alarm.

    Panic alarms must be individually enabled in the panel programming.

    :param area: 1-based area number (1-8).
    :raises ValueError: if *area* is out of range.
    """
    _validate_area(area)
    return _cmd(f"PE{area:03d}")


def encode_panic_medical(area: int) -> bytes:
    """``PM{nnn}\\r`` — trigger a medical panic alarm.

    :param area: 1-based area number (1-8).
    :raises ValueError: if *area* is out of range.
    """
    _validate_area(area)
    return _cmd(f"PM{area:03d}")


def encode_panic_fire(area: int) -> bytes:
    """``PF{nnn}\\r`` — trigger a fire panic alarm.

    :param area: 1-based area number (1-8).
    :raises ValueError: if *area* is out of range.
    """
    _validate_area(area)
    return _cmd(f"PF{area:03d}")


# ---------------------------------------------------------------------------
# Utility key
# ---------------------------------------------------------------------------


def encode_utility_key(key: int) -> bytes:
    """``UK{nnn}\\r`` — send a utility key event.

    :param key: utility key number (1-251).
    :raises ValueError: if *key* is out of range.
    """
    _validate_key(key)
    return _cmd(f"UK{key:03d}")
