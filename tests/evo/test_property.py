import time
import os
import pytest
import pprint
import re

from paradox.event import Event
from paradox.hardware.evo import Panel_EVO192

def generate_property_test_parameters():
    logfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'properties.log')
    with open(logfile, 'r') as f:
        for line in f:
            aux = line.strip().split(' ')
            if aux[1] in ["True", "False"]:
                values = [True, False]
            else:
                values = [float(aux[1])]

            aux = aux[0].split("/")
            partition = aux[1] if aux[0] == "partitions" else None

            for value in values:
                property = aux[2]
                label = aux[1]
                type = aux[0]
                yield pytest.param(property, type, value, partition, label)

def test_property_map_value():
    change = dict(property='arm',value=True,partition=1, time=time.time(), type='partition', label='Fridge')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel_EVO192.property_map)
    assert r
    assert evt.message == "Partition Fridge is armed"

def test_property_map_bad():
    change = dict(property='does_not_exist',value=True,partition=None, time=time.time(), type='system', label='alarm_in_memory')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel_EVO192.property_map)
    assert not r

@pytest.mark.parametrize("property,type,value,partition,label", generate_property_test_parameters())
def test_property(property, type, value, partition, label):
    change = dict(property=property, value=value, partition=partition, time=time.time(), type=type, label=label)
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel_EVO192.property_map)

    assert r
    assert len(evt.message) > 0
    print(evt.message)

# @pytest.mark.parametrize("property,type,value,partition,label", generate_property_test_parameters())
# def test_make_messages(property, type, value, partition, label):
#     change = dict(property=property, value=value, partition=partition, time=time.time(), type=type, label=label)
#
#     evt = Event()
#     property_map = Panel_EVO192.property_map
#     r = evt.from_change(change=change, property_map=property_map)
#     assert r
#
#     msg_part = property.replace("_", " ")
#     tags = []
#     level = "EventLevel.INFO"
#     if any(x in msg_part for x in ['trouble', 'fail', 'error']):
#         tags.append('trouble')
#         level = "EventLevel.CRITICAL"
#
#     if type == "system":
#         active_msg = "%s active"
#         inactive_msg = "%s inactive"
#         if 'trouble' in tags:
#             active_msg = "%s"
#             inactive_msg = "%s recovered"
#
#         true_ = active_msg % msg_part
#         false_ = inactive_msg % msg_part
#     else:
#         active_msg = "{Type} {label} %s active"
#         inactive_msg = "{Type} {label} %s inactive"
#         if 'trouble' in tags:
#             active_msg = "{Type} {label} %s"
#             inactive_msg = "{Type} {label} %s recovered"
#         true_ = active_msg % msg_part
#         false_ = inactive_msg % msg_part
#
#     txt = """"%s": dict(level=%s, tags=%s,
#         message={"True": "%s",
#                  "False": "%s"}),""" % (property, level, pprint.pformat(tags), true_, false_)
#
#     print(txt)
#
#     assert true_ == Panel_EVO192.property_map[property]["message"]["True"]
#     assert false_ == Panel_EVO192.property_map[property]["message"]["False"]

def test_property_map_keys():
    expected_keys = set(k.values[0] for k in generate_property_test_parameters())
    actual_keys = set(Panel_EVO192.property_map.keys())
    property_map = Panel_EVO192.property_map

    extra = actual_keys - expected_keys
    assert len(extra) == 0, "Extra keys: %s" % (", ".join(extra))
    missing = expected_keys - actual_keys
    assert len(missing) == 0, "Missing keys: %s" % (", ".join(missing))