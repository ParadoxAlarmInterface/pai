import pytest
import datetime
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
        system=dict (
            power=dict(
                label='power',
                key='power',
                id=0
            ),
            rf=dict(
                label='rf',
                key='rf',
                id=1
            ),
            troubles=dict(
                label='troubles',
                key='troubles',
                id=2
            )
        ),
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
        troubles=dict(
            time_loss_trouble=False,
            fire_loop_trouble=False,
            power_trouble=False,
            ac_fail_trouble=False
        ),   
        system=dict(
            time=datetime.datetime(2019, 9, 14, 8, 55), 
            vdc=16.816470588235294, 
		    dc=13.769411764705884, 
		    battery=13.411764705882353
        ),
        rf=dict(
            noise_floor=63
        ),
        zone={
            1: dict(
                open=False,
                tamper=False,
                was_in_alarm=False,
                alarm=False,
                bypassed=False, 
                entry_delay=False,
                fire_delay=False,
                no_delay=True
                ),
            2: dict(
                open=True,
                tamper=False,
                was_in_alarm=False,
                alarm=False,
                bypassed=False, 
                entry_delay=False,
                fire_delay=False,
                no_delay=True
                ),
            3: dict(
                open=False,
                tamper=False,
                was_in_alarm=False,
                alarm=False,
                bypassed=False, 
                entry_delay=False,
                fire_delay=False,
                no_delay=True
            )
        },
        pgm={
            1: dict(
                tamper=False,
                supervision_trouble=False,
                signal_stength=0
            )
        },
        bus_module={
            1: dict(
                tamper=False,
                supervision_trouble=False
            )
        },
        partition={
            1: dict(
                alarm=False,
                pulse_fire_alarm=False,
                arm_stay=False,
                arm_sleep=False,
                arm=False
            ),
            2: dict(
                alarm=False,
                pulse_fire_alarm=False,
                arm_stay=False,
                arm_sleep=False,
                arm=False
            )
        },
    ))

@pytest.mark.asyncio
async def test_homie_initial_setup_filtered(mocker):
    interface = HomieMQTTInterface()
    #mocker.patch.object(interface,"run")
    interface.start()
    interface.node_filter = {
                        'zone'      :['open', 'alarm'],
                        'system'    :['vdc', 'dc','battery']
                    }

    await interface._started.wait()
    send_initial_status()

@pytest.mark.asyncio
async def test_homie_initial_setup_all(mocker):
    interface = HomieMQTTInterface()
    #mocker.patch.object(interface,"run")
    interface.start()
    interface.node_filter = {
                        'zone'      :['open', 'alarm'],
                        'system'    :['all']
                    }

    await interface._started.wait()
    send_initial_status()