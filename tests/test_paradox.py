from mock import MagicMock

from paradox.paradox import Paradox

from paradox.lib.ps import sendMessage
from paradox.models.element_type_container import ElementTypeContainer


def send_initial_status(alarm):
    sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            )
        }
    ))

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=False
            )
        }
    ))

    alarm.update_properties.assert_called_with('partition', 'Partition_1', {'current_state': 'disarmed'})


def test_current_state_armed_away():
    alarm = Paradox(None)
    alarm.update_properties = MagicMock()

    send_initial_status(alarm)

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True
            )
        }
    ))
    alarm.update_properties.assert_called_with('partition', 'Partition_1', {'current_state': 'armed_away'})


def test_current_state_pending():
    alarm = Paradox(None)
    alarm.update_properties = MagicMock()

    send_initial_status(alarm)

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True,
                exit_delay=True
            )
        }
    ))
    alarm.update_properties.assert_called_with('partition', 'Partition_1', {'current_state': 'pending'})


def test_current_arm_stay():
    alarm = Paradox(None)
    alarm.update_properties = MagicMock()

    send_initial_status(alarm)

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=True,
                arm_stay=True
            )
        }
    ))
    alarm.update_properties.assert_called_with('partition', 'Partition_1', {'current_state': 'armed_home'})


def test_current_alarm(mocker):
    alarm = Paradox(None)
    alarm.update_properties = MagicMock()

    send_initial_status(alarm)

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                audible_alarm=True
            )
        }
    ))
    alarm.update_properties.assert_called_with('partition', 'Partition_1', {'current_state': 'triggered'})


def test_on_labels_load(mocker):
    alarm = Paradox(None)

    sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            )
        }
    ))

    assert isinstance(alarm.data['partition'], ElementTypeContainer)

    assert alarm.data['partition']['Partition_1'] == dict(
        id=1,
        label='Partition 1',
        key='Partition_1'
    )