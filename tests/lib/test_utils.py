from construct import Container, ListContainer
from paradox.lib.utils import construct_free, deep_merge, sanitize_key


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
    assert sanitize_key("Előtér") == "Előtér"

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
