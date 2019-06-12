import time
import os

from paradox.event import Event
from paradox.hardware.spectra_magellan import Panel

def test_property_map_value():

    change = dict(property='dc',value=3.33,partition=None, time=time.time(), type='system', label='power')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    assert r
    assert evt.message == "DC voltage is 3.33V"

def test_property_map_bad():
    change = dict(property='dcd',value=3.33,partition=None, time=time.time(), type='system', label='power')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    assert not r


def test_all_properties():
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

                change = dict(property=aux[2], value=value, partition=partition, time=time.time(), type=aux[0], label=aux[1])
                evt = Event()
                r = evt.from_change(change=change, property_map=Panel.property_map)

                assert r
                assert len(evt.message) > 0

