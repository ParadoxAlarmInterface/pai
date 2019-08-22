from pytest_mock import mocker

from paradox.interfaces.mqtt_interface import MQTTInterface

def test_hass_from_arm_stay_to_arm(mocker):
    interface = MQTTInterface()

    mocker.patch.object(interface, "mqtt")

    change = {
        'property': 'arm_stay',
        'label': 'Partiton 1',
        'value': True,
        'initial': False,
        'type': "partition"
    }

    interface.handle_panel_change(change)

    interface.mqtt.publish.assert_called_with('paradox/states/partitions/Partiton_1/current_hass', 'armed_home', 0, True)

    change1 = {
        'property': 'arm',
        'label': 'Partiton 1',
        'value': True,
        'initial': False,
        'type': "partition"
    }

    interface.handle_panel_change(change1)

    interface.mqtt.publish.assert_called_with('paradox/states/partitions/Partiton_1/current_hass', 'armed_away', 0, True)

def test_hass_from_arm_to_disarm(mocker):
    interface = MQTTInterface()

    mocker.patch.object(interface, "mqtt")

    change = {
        'property': 'arm',
        'label': 'Partiton 1',
        'value': True,
        'initial': False,
        'type': "partition"
    }

    interface.handle_panel_change(change)

    interface.mqtt.publish.assert_called_with('paradox/states/partitions/Partiton_1/current_hass', 'armed_away', 0, True)

    change1 = {
        'property': 'arm',
        'label': 'Partiton 1',
        'value': False,
        'initial': False,
        'type': "partition"
    }

    interface.handle_panel_change(change1)

    interface.mqtt.publish.assert_called_with('paradox/states/partitions/Partiton_1/current_hass', 'disarmed', 0, True)