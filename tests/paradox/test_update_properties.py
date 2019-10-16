from paradox.event import EventLevel
from paradox.lib import ps
from paradox.paradox import Paradox


def test_partitions(mocker):
    alarm = Paradox()
    alarm.panel = mocker.MagicMock()
    alarm.panel.property_map = {
        "arm": dict(level=EventLevel.INFO,
                    message={"True": "{Type} {label} is armed",
                             "False": "{Type} {label} is disarmed"}),
    }

    event = mocker.MagicMock()
    mocker.patch.object(ps, "sendChange")
    mocker.patch.object(ps, "sendEvent")
    mocker.patch('paradox.paradox.event.Event.from_change', return_value=event)

    ps.sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            )
        }
    ))

    assert isinstance(alarm.panel, mocker.MagicMock)

    alarm.update_properties("partition", "Partition_1", change=dict(arm=True))

    ps.sendChange.assert_called_once_with('partition', 'Partition_1', 'arm', True, initial=True)
    ps.sendChange.reset_mock()

    assert isinstance(alarm.panel, mocker.MagicMock)

    ps.sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=False
            )
        }
    ))

    assert isinstance(alarm.panel, mocker.MagicMock)

    ps.sendChange.assert_any_call('partition', 'Partition_1', 'current_state', 'disarmed', initial=True)
    ps.sendChange.assert_any_call('partition', 'Partition_1', 'arm', False)
    assert ps.sendChange.call_count == 2

    ps.sendEvent.assert_called_once_with(event)


def test_partitions_callable_prop(mocker):
    alarm = Paradox()
    alarm.panel = mocker.MagicMock()
    alarm.panel.property_map = {
        "arm": dict(level=EventLevel.INFO,
                    message={"True": "{Type} {label} is armed",
                             "False": "{Type} {label} is disarmed"}),
    }

    event = mocker.MagicMock()
    mocker.patch.object(ps, "sendChange")
    mocker.patch.object(ps, "sendEvent")
    mocker.patch('paradox.paradox.event.Event.from_change', return_value=event)

    ps.sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            )
        }
    ))

    ps.sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=False
            )
        }
    ))

    ps.sendChange.assert_any_call('partition', 'Partition_1', 'arm', False, initial=True)
    ps.sendChange.reset_mock()

    alarm.update_properties("partition", "Partition_1", change=dict(arm=lambda old: not old))
    ps.sendChange.assert_any_call('partition', 'Partition_1', 'arm', True)

    ps.sendEvent.assert_called_once_with(event)