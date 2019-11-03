from construct import Container

from paradox.lib.utils import deep_merge


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
