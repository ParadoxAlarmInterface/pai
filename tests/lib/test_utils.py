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


def test_deep_merge_extend_lists():
    cs = [Container(a=[1, 2]), Container(a=[3])]

    result = deep_merge(*cs, extend_lists=True)
    assert dict(a=[1, 2, 3]) == result
