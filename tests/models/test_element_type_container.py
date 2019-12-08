import pytest

from paradox.data.element_type_container import ElementTypeContainer


def test_get_by_key():
    a = ElementTypeContainer({1: {'key': 'Living_room', 'val': 25}})

    assert a['Living_room'] == {'key': 'Living_room', 'val': 25}


def test_deep_merge():
    a = ElementTypeContainer({1: {'key': 'Living_room', 'val': 25}})
    a.deep_merge({1: {'beer': 10}})

    assert a[1] == {'key': 'Living_room', 'val': 25, 'beer': 10}


def test_set_by_string_key():
    a = ElementTypeContainer({1: {'key': 'Living_room', 'val': 25}})
    a['1'] = {'key': 'Living_room', 'val': 17}

    assert a['Living_room'] == {'key': 'Living_room', 'val': 17}


def test_filter():
    a = ElementTypeContainer({1: {'key': 'Living_room'}, 2: {'key': 'Kids_room'}})
    assert len(a) == 2
    a.filter([1])

    assert a[1] == {'key': 'Living_room'}
    assert len(a) == 1
    with pytest.raises(KeyError):
        assert a[2] == {'key': 'Kids_room'}


def test_hole():
    a = ElementTypeContainer({1: {'key': 'Living_room'}, 3: {'key': 'Kids_room'}})

    assert 1 in a
    assert 3 in a

    assert 'Kids_room' in a
    assert 'Living_room' in a


def test_repr():
    a = ElementTypeContainer({1: {'key': 'Living_room'}, 3: {'key': 'Kids_room'}})

    assert a.__repr__() == "{1: {'key': 'Living_room'}, 3: {'key': 'Kids_room'}}"
    assert a.__str__() == "{1: {'key': 'Living_room'}, 3: {'key': 'Kids_room'}}"


def test_del():
    a = ElementTypeContainer({1: {'key': 'Living_room'}, 3: {'key': 'Kids_room'}})

    del a['Kids_room']

    assert a == {1: {'key': 'Living_room'}}


def test_update():
    a = ElementTypeContainer({1: {'key': 'Living_room'}})

    a.deep_merge({3: {'key': 'Kids_room'}})
    a.deep_merge({1: {'label': 'Living room'}})

    assert a == {1: {'key': 'Living_room', 'label': 'Living room'}, 3: {'key': 'Kids_room'}}


def test_select():
    a = ElementTypeContainer({1: {'key': 'Living_room', 'id': 1}, 3: {'key': 'Kids_room', 'id': 3}})

    assert a.select('all') == [1, 3]
    assert a.select('0') == [1, 3]

    assert a.select('Living_room') == [1]

    assert a.select('1') == [1]
