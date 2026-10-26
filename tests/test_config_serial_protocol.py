"""``SERIAL_PROTOCOL`` and its interplay with ``SERIAL_ENCRYPTED``."""

from typing import Dict, Optional, Tuple

import pytest

from paradox import config as config_module
from paradox.config import Config
from paradox.connections.ip.connection import BareIPConnection, E0FEBareIPConnection
from paradox.connections.serial.connection import (
    E0FESerialCommunication,
    SerialCommunication,
)
from paradox.paradox import Paradox


@pytest.fixture(autouse=True)
def no_environment(monkeypatch):
    monkeypatch.delenv("PAI_SERIAL_PROTOCOL", raising=False)
    monkeypatch.delenv("PAI_SERIAL_ENCRYPTED", raising=False)
    monkeypatch.delenv("PAI_PASSWORD", raising=False)


def load(monkeypatch, entries: dict) -> Config:
    c = Config()
    monkeypatch.setattr(c, "_find_config", lambda loc=None: None)
    monkeypatch.setattr(c, "_read_config", lambda: entries)
    c.load()
    return c


@pytest.mark.parametrize(
    "entries, protocol",
    [
        ({}, "plain"),
        ({"SERIAL_ENCRYPTED": False}, "plain"),
        ({"SERIAL_ENCRYPTED": True, "PASSWORD": "1234"}, "aes"),
        ({"SERIAL_PROTOCOL": "plain"}, "plain"),
        ({"SERIAL_PROTOCOL": "plain", "SERIAL_ENCRYPTED": False}, "plain"),
        ({"SERIAL_PROTOCOL": "aes", "PASSWORD": "1234"}, "aes"),
        (
            {"SERIAL_PROTOCOL": "aes", "SERIAL_ENCRYPTED": True, "PASSWORD": "1234"},
            "aes",
        ),
        ({"SERIAL_PROTOCOL": "e0fe"}, "e0fe"),
        ({"SERIAL_PROTOCOL": "e0fe", "SERIAL_ENCRYPTED": False}, "e0fe"),
    ],
)
def test_serial_protocol(monkeypatch, entries, protocol):
    monkeypatch.setattr(config_module, "config", load(monkeypatch, entries))
    assert config_module.get_serial_protocol() == protocol


@pytest.mark.parametrize(
    "entries",
    [
        {"SERIAL_PROTOCOL": "e0fe", "SERIAL_ENCRYPTED": True},
        {"SERIAL_PROTOCOL": "plain", "SERIAL_ENCRYPTED": True},
        {"SERIAL_PROTOCOL": "aes", "SERIAL_ENCRYPTED": False, "PASSWORD": "1234"},
        {"SERIAL_PROTOCOL": "aes"},
        {"SERIAL_PROTOCOL": "e0fe", "IP_INTERFACE_ENABLE": True},
    ],
)
def test_conflict_rejected(monkeypatch, entries):
    with pytest.raises(ValueError, match="SERIAL_PROTOCOL"):
        load(monkeypatch, entries)


def test_unknown_value_rejected(monkeypatch):
    with pytest.raises(Exception, match="SERIAL_PROTOCOL"):
        load(monkeypatch, {"SERIAL_PROTOCOL": "auto"})


def test_from_environment(monkeypatch):
    monkeypatch.setenv("PAI_SERIAL_PROTOCOL", "e0fe")
    assert load(monkeypatch, {}).SERIAL_PROTOCOL == "e0fe"


def test_connection_class_follows_serial_protocol(monkeypatch):
    def connection_for(connection_type: str, protocol: Optional[str]) -> type:
        monkeypatch.setattr(config_module.config, "CONNECTION_TYPE", connection_type)
        monkeypatch.setattr(config_module.config, "SERIAL_PROTOCOL", protocol)
        monkeypatch.setattr(config_module.config, "IP_CONNECTION_BARE", True)
        return type(Paradox().connection)

    expected: Dict[Tuple[str, Optional[str]], type] = {
        ("Serial", "e0fe"): E0FESerialCommunication,
        ("Serial", "plain"): SerialCommunication,
        ("Serial", None): SerialCommunication,
        ("IP", "e0fe"): E0FEBareIPConnection,
        ("IP", "aes"): BareIPConnection,
        ("IP", None): BareIPConnection,
    }
    for key, cls in expected.items():
        assert connection_for(*key) is cls, key
