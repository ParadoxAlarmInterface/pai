import pytest

from datetime import datetime

from paradox.data.element_type_container import ElementTypeContainer


def test_get():
    d = datetime.now()
    a = ElementTypeContainer(date=dict(time=d))

    assert a["date"]["time"] == d

    with pytest.raises(KeyError):
        a["date"]["not_found"]


def test_get_by_key():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    assert a["El 1"]["key"] == "El 1"

    assert a["1"]["key"] == "El 1"

    assert a[1]["key"] == "El 1"


def test_set():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    a["El 1"]["test"] = "one"
    assert a[1]["test"] == "one"

    a[1]["test"] = "two"
    assert a["El 1"]["test"] == "two"


def test_contains():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})
    assert "El 1" in a
    assert 1 in a


def test_select():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    assert len(a.select("all")) == 2
    assert a.select("all") == [1, 2]
    assert len(a.select("0")) == 2
    assert a.select("0") == [1, 2]

    assert len(a.select("2")) == 1
    assert a.select("2") == [2]
    assert len(a.select("El 2")) == 1
    assert a.select("El 2") == [2]
