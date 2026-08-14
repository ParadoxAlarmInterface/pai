import json

from construct import Container, ListContainer
import pytest

from paradox.lib.utils import (
    SerializableToJSONEncoder,
    construct_free,
    deep_merge,
    describe_connection,
    format_duration,
    mask_email,
    mask_secret,
    sanitize_key,
)


def test_deep_merge():
    cs = [Container(a="a"), Container(c="a", d="b"), Container(e="c")]

    result = deep_merge(*cs)
    assert dict(a="a", c="a", d="b", e="c") == result


def test_deep_merge_deep():
    cs = [Container(a=Container(c="a", d=Container(e="c")))]

    result = deep_merge(*cs)
    assert dict(a=dict(c="a", d=dict(e="c"))) == result


def test_deep_merge_deep_keep_first_container_changed():
    cs = [Container(a="a"), Container(c="a", d="b"), Container(e="c")]
    first_container = cs[0].copy()

    result = deep_merge(*cs)
    assert dict(a="a", c="a", d="b", e="c") == result
    assert cs[0] != first_container


def test_deep_merge_deep_keep_first_container_left_intact():
    cs = [Container(a="a"), Container(c="a", d="b"), Container(e="c")]
    first_container = cs[0].copy()

    result = deep_merge(*cs, initializer={})
    assert dict(a="a", c="a", d="b", e="c") == result
    assert cs[0] == first_container


def test_deep_merge_extend_lists():
    cs = [Container(a=[1, 2]), Container(a=[3])]

    result = deep_merge(*cs, extend_lists=True)
    assert dict(a=[1, 2, 3]) == result


def test_sanitize_key():
    assert sanitize_key("Előtér") == "Eloter"

    assert sanitize_key("Living room") == "Living_room"

    assert sanitize_key(1) == "1"


def test_construct_free():
    a = Container(a=Container(test="this", _io="beer2"), _io="beer")

    r = construct_free(a)
    assert isinstance(r, dict)
    assert isinstance(r["a"], dict)

    a = Container(a=ListContainer([Container(test="this", _io="beer2")]), _io="beer")

    r = construct_free(a)
    assert isinstance(r, dict)
    assert isinstance(r["a"], list)


def test_json_serialization():
    class TestEntity:
        def serialize(self):
            return dict(a="b")

    data = {1: TestEntity()}

    assert '{"1": {"a": "b"}}' == json.dumps(data, cls=SerializableToJSONEncoder)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("7106152c", "****152c"),
        (b"\x71\x06\x15\x2c", "****152c"),
        ("abc", "****"),
        ("", "****"),
        (None, "****"),
        (1234567, "****4567"),
    ],
)
def test_mask_secret(value, expected):
    assert mask_secret(value) == expected


def test_mask_secret_keep_zero():
    assert mask_secret("7106152c", keep=0) == "****"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("john@example.com", "j****@e****.com"),
        ("a@b.io", "a****@b****.io"),
        ("notanemail", "****"),
        ("", "****"),
        (None, "****"),
    ],
)
def test_mask_email(value, expected):
    assert mask_email(value) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (None, "unknown"),
        (0, "0s"),
        (0.4, "0s"),
        (45, "45s"),
        (60, "1m"),
        (723, "12m 3s"),
        (3600, "1h"),
        (8040, "2h 14m"),
        (315000, "3d 15h"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


class _Cfg:
    def __init__(self, **kwargs):
        self.CONNECTION_TYPE = "IP"
        self.SERIAL_PORT = "/dev/ttyS1"
        self.SERIAL_BAUD = 9600
        self.PRT3_SERIAL_PORT = "/dev/ttyUSB0"
        self.PRT3_SERIAL_BAUD = 57600
        self.IP_CONNECTION_HOST = "192.168.1.10"
        self.IP_CONNECTION_PORT = 10000
        self.IP_CONNECTION_BARE = False
        self.IP_CONNECTION_SITEID = None
        self.IP_CONNECTION_EMAIL = None
        self.IP_CONNECTION_PANEL_SERIAL = None
        self.__dict__.update(kwargs)


def test_describe_connection_serial():
    assert (
        describe_connection(_Cfg(CONNECTION_TYPE="Serial")) == "Serial(/dev/ttyS1@9600)"
    )


def test_describe_connection_prt3():
    assert (
        describe_connection(_Cfg(CONNECTION_TYPE="PRT3")) == "PRT3(/dev/ttyUSB0@57600)"
    )


def test_describe_connection_local_ip():
    assert describe_connection(_Cfg()) == "IP(192.168.1.10:10000)"


def test_describe_connection_bare_ip():
    assert (
        describe_connection(_Cfg(IP_CONNECTION_BARE=True))
        == "IP-bare(192.168.1.10:10000)"
    )


def test_describe_connection_site_masks_secrets():
    cfg = _Cfg(
        IP_CONNECTION_SITEID="MySite",
        IP_CONNECTION_EMAIL="john@example.com",
        IP_CONNECTION_PANEL_SERIAL="7106152c",
    )
    result = describe_connection(cfg)

    assert result == "SITE(MySite / j****@e****.com, serial ****152c)"
    assert "john@example.com" not in result
    assert "7106152c" not in result


def test_describe_connection_unknown():
    assert (
        describe_connection(_Cfg(CONNECTION_TYPE="Carrier Pigeon"))
        == "Unknown(Carrier Pigeon)"
    )
