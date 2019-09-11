import pytest
from pytest_mock import mocker

from paradox.interfaces.homie_mqtt_interface import HomieMQTTInterface

from paradox.lib.ps import sendMessage


# def test_handle_panel_change(mocker):
#     cp = HomieMQTTInterface(mocker)

#     change = {}
#     change['property'] = 'open'
#     change['label'] = "Zone 01"
#     change['value'] = True
#     change['initial'] = True
#     change['type'] = 'zone'

#     cp.handle_panel_change(change)

def send_initial_status():
    sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partiton 1',
                key='Partiton_1'
            )
        },
        zone={
            1: dict(
                id=1,
                label='Front door reed',
                key='Front_door_reed'
            ),
            2: dict(
                id=2,
                label='Main door',
                key='Main_door'
            )
        }

    ))

    #need to figure out the structure here.  For power (battery, vdc, dc) and zones (open, alarm)
    sendMessage("status_update", status=dict(
        partition_status={
            1: dict(
                arm=False
            )
        }
    ))

@pytest.mark.asyncio
async def test_homie_pending(mocker):
    interface = HomieMQTTInterface()
    #mocker.patch.object(interface,"run")
    interface.start()

    await interface._started.wait()
    send_initial_status()