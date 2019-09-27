import pytest
from paradox.models.element_type_container import ElementTypeContainer

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