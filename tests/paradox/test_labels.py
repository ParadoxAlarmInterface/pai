from paradox.lib.ps import sendMessage
from paradox.data.element_type_container import ElementTypeContainer
from paradox.paradox import Paradox


def test_on_labels_load():
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

    assert isinstance(alarm.storage.get_container('partition'), ElementTypeContainer)

    assert alarm.storage.get_container_object('partition', 'Partition_1') == dict(
        id=1,
        label='Partition 1',
        key='Partition_1'
    )