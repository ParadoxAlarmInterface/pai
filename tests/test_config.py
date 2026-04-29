import pytest
from unittest.mock import patch, mock_open

from paradox.config import config as cfg, get_limits_for_type

def test_get_limits_for_type_for_auto(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": 'auto',
        }
    )


    assert get_limits_for_type('partition') == None
    assert get_limits_for_type('partition', []) == []


def test_get_limits_for_type_for_specified_string_range(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": '1-4',
        }
    )


    assert get_limits_for_type('partition') == [1,2,3,4]
    assert get_limits_for_type('partition', []) == [1,2,3,4]


def test_get_limits_for_type_for_specified_string_list(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": '1,4',
        }
    )


    assert get_limits_for_type('partition') == [1,4]
    assert get_limits_for_type('partition', []) == [1,4]


def test_get_limits_for_type_for_specified_py_range(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": range(1,5),
        }
    )


    assert get_limits_for_type('partition') == [1,2,3,4]
    assert get_limits_for_type('partition', []) == [1,2,3,4]


def test_get_limits_for_type_for_specified_py_list(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": [1,2],
        }
    )


    assert get_limits_for_type('partition') == [1,2]
    assert get_limits_for_type('partition', []) == [1,2]


def test_get_limits_for_type_for_specified_py_None(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={}
    )


    assert get_limits_for_type('partition') == None
    assert get_limits_for_type('partition', []) == []


def test_get_limits_for_type_for_specified_empty_string(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            'partition': ''
        }
    )


    assert get_limits_for_type('partition') == []
    assert get_limits_for_type('partition', [1,2]) == []


# ---------------------------------------------------------------------------
# PRT3 config validation
# ---------------------------------------------------------------------------

def _make_config(monkeypatch, entries: dict):
    """Return a fresh Config instance loaded with the given entries dict."""
    from paradox.config import Config
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: entries)
    c.load()
    return c


def test_prt3_user_code_empty_accepted(monkeypatch):
    """Empty PRT3_USER_CODE is valid (quick-arm mode)."""
    c = _make_config(monkeypatch, {"PRT3_USER_CODE": ""})
    assert c.PRT3_USER_CODE == ""


def test_prt3_user_code_digits_accepted(monkeypatch):
    """A 1–6 digit code is valid."""
    c = _make_config(monkeypatch, {"PRT3_USER_CODE": "123456"})
    assert c.PRT3_USER_CODE == "123456"


def test_prt3_user_code_invalid_alpha_rejected(monkeypatch):
    """Alphabetic PRT3_USER_CODE raises at load time."""
    from paradox.config import Config
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: {"PRT3_USER_CODE": "abc"})
    with pytest.raises(ValueError, match="PRT3_USER_CODE"):
        c.load()


def test_prt3_user_code_too_long_rejected(monkeypatch):
    """A 7-digit code raises at load time."""
    from paradox.config import Config
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: {"PRT3_USER_CODE": "1234567"})
    with pytest.raises(ValueError, match="PRT3_USER_CODE"):
        c.load()


def test_prt3_serial_baud_valid_accepted(monkeypatch):
    """9600 and 19200 are the only valid PRT3 baud rates."""
    for baud in (9600, 19200):
        c = _make_config(monkeypatch, {"PRT3_SERIAL_BAUD": baud})
        assert c.PRT3_SERIAL_BAUD == baud


def test_prt3_serial_baud_38400_rejected(monkeypatch):
    """38400 is not a valid PRT3 baud rate and must raise at load time."""
    from paradox.config import Config
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: {"PRT3_SERIAL_BAUD": 38400})
    with pytest.raises(Exception, match="PRT3_SERIAL_BAUD"):
        c.load()