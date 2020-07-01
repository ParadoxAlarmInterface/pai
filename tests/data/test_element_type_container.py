from datetime import datetime

import pytest

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


def test_get_index():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    assert a.get_index("El 1") == 1
    assert a.get_index(1) == 1

    b = ElementTypeContainer({"test": {"key": "El 1"}, "other": {"key": "El 2"}})

    assert b.get_index("other") == "other"
    assert b.get_index("test") == "test"


def test_set():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    a["El 1"]["test"] = "one"
    assert a[1]["test"] == "one"

    a[1]["test"] = "two"
    assert a["El 1"]["test"] == "two"


def test_delete():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    del a["El 1"]

    assert a["El 2"]["key"] == "El 2"
    with pytest.raises(KeyError):
        a["El 1"]


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

    assert len(a.select([1, 2])) == 2
    assert a.select([1, 2]) == [1, 2]
    assert a.select(["El 1", "El 2"]) == [1, 2]


def test_filter():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})

    a.filter(["El 1", "El 2"])

    assert len(a) == 2

    a.filter(["El 1"])  # drops El 2

    assert len(a) == 1

    a.filter([1])

    assert len(a) == 1

    a.filter([2])  # 2 does not exist

    assert len(a) == 0


def test_text_index_updates():
    a = ElementTypeContainer({1: {"key": "El 1"}, 2: {"key": "El 2"}})
    assert len(a.key_index) == 2

    a[3] = {"key": "El 3"}
    assert len(a.key_index) == 3

    a.filter([1, 3])

    assert len(a.key_index) == 2

    assert a["El 1"]["key"] == "El 1"
    assert a["El 3"]["key"] == "El 3"
    with pytest.raises(KeyError):
        a[2]

    del a["El 1"]
    assert len(a.key_index) == 1

    with pytest.raises(KeyError):
        a[1]
