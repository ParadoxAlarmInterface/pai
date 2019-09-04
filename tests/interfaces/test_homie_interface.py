from mock import call
from pytest_mock import mocker

from paradox.interfaces.homie_mqtt_interface import HomieMQTTInterface

def test_handle_panel_change(mocker):
    cp = HomieMQTTInterface(mocker)

    change = {}
    change['property'] = 'open'
    change['label'] = "Zone 01"
    change['value'] = True
    change['initial'] = True
    change['type'] = 'zone'

    cp.handle_panel_change(change)