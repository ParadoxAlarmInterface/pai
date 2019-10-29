from paradox.event import EventLevel, Change
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
    mocker.patch("paradox.lib.ps.sendChange")
    mocker.patch("paradox.lib.ps.sendEvent")
    mocker.patch('paradox.event.ChangeEvent', return_value=event)

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

    alarm.storage.update_container_object("partition", "Partition_1", dict(arm=True))

    ps.sendChange.assert_called_once_with(Change('partition', 'Partition_1', 'arm', True, initial=True))
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

    ps.sendChange.assert_any_call(Change('partition', 'Partition_1', 'current_state', 'disarmed', initial=True))
    ps.sendChange.assert_any_call(Change('partition', 'Partition_1', 'arm', False, initial=False))
    assert ps.sendChange.call_count == 2

    assert ps.sendEvent.call_count == 0


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
    mocker.patch('paradox.event.ChangeEvent', return_value=event)

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

    ps.sendChange.assert_any_call(Change('partition', 'Partition_1', 'arm', False, initial=True))
    ps.sendChange.reset_mock()

    alarm.storage.update_container_object("partition", "Partition_1", dict(arm=lambda old: not old))
    ps.sendChange.assert_any_call(Change('partition', 'Partition_1', 'arm', True))

    ps.sendEvent.call_count = 0