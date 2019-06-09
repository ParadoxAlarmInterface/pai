import pytest
import time

from paradox.event import Event
from paradox.hardware.spectra_magellan import Panel

def test_property_map_bool():

    change = dict(property='timer_loss_trouble',value=True,partition=None, time=time.time(), type='system',label='trouble')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    assert r
    assert evt.message == "Timer lost trouble"
    
    change = dict(property='timer_loss_trouble',value=False,partition=None, time=time.time(), type='system', label='trouble')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    
    assert r
    assert evt.message == "Timer recovered"

def test_property_map_label():

    change = dict(property='zone_status',value=True,partition=None, time=time.time(), type='zone',label='OUTSIDE')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    
    assert r
    assert evt.message == "Zone OUTSIDE Open"

def test_property_map_value():

    change = dict(property='dc',value=3.33,partition=None, time=time.time(), type='system', label='power')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    assert r
    assert evt.message == "DC voltage is 3.33"

def test_property_map_bad():
    change = dict(property='dcd',value=3.33,partition=None, time=time.time(), type='system', label='power')
    evt = Event()
    r = evt.from_change(change=change, property_map=Panel.property_map)
    assert not r

