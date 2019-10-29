import time
import os
import pytest

from paradox.event import ChangeEvent, Change
from paradox.hardware.spectra_magellan import Panel

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
    change = Change(property='dc',new_value=3.33, type='system', key='power')
    evt = ChangeEvent(change_object=change, property_map=Panel.property_map)
    assert evt
    assert evt.message == "DC voltage is 3.33V"

def test_property_map_bad():
    change = Change(property='dcd', new_value=3.33, type='system', key='power')
    with pytest.raises(AssertionError):
        ChangeEvent(change_object=change, property_map=Panel.property_map)

def test_partition_arm_message():
    change = Change(property='arm', new_value=True, type='partition', key='Fridge')
    evt = ChangeEvent(change_object=change, property_map=Panel.property_map)
    assert evt
    assert evt.message == "Partition Fridge is armed"

@pytest.mark.parametrize("type,property,value,partition,label", generate_property_test_parameters())
def test_property(type, property, value, partition, label):
    change = Change(property=property, new_value=value, type=type, key=label)
    evt = ChangeEvent(change_object=change, property_map=Panel.property_map)

    assert evt
    assert len(evt.message) > 0

