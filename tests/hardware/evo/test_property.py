import os
import pytest

from paradox.event import ChangeEvent, Change
from paradox.hardware.evo import Panel_EVO192

def generate_property_test_parameters():
    logfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'properties.log')
    with open(logfile, 'r') as f:
        for line in f:
            aux = line.strip().split(' ', 1)
            if aux[1] in ["True", "False"]:
                values = [True, False]
            else:
                try:
                    values = [float(aux[1])]
                except ValueError:
                    values = [aux[1]]

            aux = aux[0].split("/")
            partition = aux[1] if aux[0] == "partitions" else None

            for value in values:
                property = aux[2]
                label = aux[1]
                type = aux[0]
                yield pytest.param(type, property, value, partition, label)

def test_property_map_value():
    change = Change(property='arm', new_value=True, old_value=None, type='partition', key='Fridge')
    evt = ChangeEvent(change_object=change, property_map=Panel_EVO192.property_map)
    assert evt
    assert evt.message == "Partition Fridge is armed"

def test_property_map_bad():
    change = Change(property='does_not_exist', new_value=True, old_value=None, type='system', key='alarm_in_memory')
    with pytest.raises(AssertionError):
        ChangeEvent(change_object=change, property_map=Panel_EVO192.property_map)

@pytest.mark.parametrize("type,property,value,partition,label", generate_property_test_parameters())
def test_property(property, type, value, partition, label):
    change = Change(property=property, new_value=value, old_value=None, type=type, key=label)
    evt = ChangeEvent(change_object=change, property_map=Panel_EVO192.property_map)

    assert evt
    assert len(evt.message) > 0
    print(evt.message)

# @pytest.mark.parametrize("property,type,value,partition,label", generate_property_test_parameters())
# def test_make_messages(property, type, value, partition, label):
#     change = dict(property=property, value=value, partition=partition, time=time.time(), type=type, label=label)
#
#     property_map = Panel_EVO192.property_map
#     evt = Event.from_change(change=change, property_map=property_map)
#     assert evt
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
    synthetic_props = ['current_state']
    expected_keys = set(k.values[1] for k in generate_property_test_parameters())
    expected_keys.update(synthetic_props)
    actual_keys = set(Panel_EVO192.property_map.keys())
    # property_map = Panel_EVO192.property_map

    extra = actual_keys - expected_keys
    assert len(extra) == 0, "Extra keys: %s" % (", ".join(extra))
    missing = expected_keys - actual_keys
    assert len(missing) == 0, "Missing keys: %s" % (", ".join(missing))