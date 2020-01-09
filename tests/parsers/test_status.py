import datetime
from paradox.lib import ps

from paradox.paradox import Paradox
from paradox.parsers.status import convert_raw_status

evo_status = {
    '_weekday': 5,
    'pgm_flags': dict(chime_zone_partition={1: False, 2: False},
                      power_smoke=False,
                      ground_start=False, kiss_off=False, line_ring=False,
                      bell_partition={1: False, 2: False},
                      fire_alarm={1: False, 2: False},
                      open_close_kiss_off={1: False, 2: False}),
    'key-switch_triggered': {1: False, 2: False},
    'door_open': {1: False, 2: False},
    '_time': datetime.datetime(2019, 9, 12, 11, 37, 5),
    'zone_open': {1: False, 2: False},
    'zone_tamper': {1: False, 2: False},
    'zone_low_battery': {1: False, 2: False},
    'zone_status': {
        1: dict(generated_alarm=False, presently_in_alarm=False, activated_entry_delay=False,
                activated_intellizone_delay=False, bypassed=False, shutted_down=False,
                tx_delay=False, supervision_trouble=False),
        2: dict(generated_alarm=False,
                presently_in_alarm=False,
                activated_entry_delay=False,
                activated_intellizone_delay=False,
                bypassed=False,
                shutted_down=False,
                tx_delay=False,
                supervision_trouble=False)
    },
    'partition_status': {
        1: dict(fire_alarm=False, audible_alarm=False, silent_alarm=False, was_in_alarm=False, arm_no_entry=False,
                arm_stay=False, arm_away=False, arm=False, lockout=False, programming=False, zone_bypassed=False,
                alarm_in_memory=True, trouble=True, entry_delay=False, exit_delay=False, ready=True,
                zone_supervision_trouble=False, zone_fire_loop_trouble=False, zone_low_battery_trouble=False,
                zone_tamper_trouble=False, voice_arming=False, auto_arming_engaged=False,
                fire_delay_in_progress=False, intellizone_engage=False, time_to_refresh_zone_status=False,
                panic_alarm=False, police_code_delay=False, follow_become_delay=False, remote_arming=False,
                stay_arming_auto=False, partition_recently_close=False, cancel_alarm_reporting_on_disarming=False,
                tx_delay_finished=False, auto_arm_reach=False, fire_delay_end=False, no_movement_delay_end=False,
                alarm_duration_finished=False, entry_delay_finished=False, exit_delay_finished=False,
                intellizone_delay_finished=False, all_zone_closed=True, inhibit_ready=True, bypass_ready=True,
                force_ready=True, stay_instant_ready=True),
        2: dict(fire_alarm=False, audible_alarm=False,
                silent_alarm=False, was_in_alarm=False,
                arm_no_entry=False, arm_stay=False,
                arm_away=False, arm=False, lockout=False,
                programming=False, zone_bypassed=False,
                alarm_in_memory=False, trouble=True,
                entry_delay=False, exit_delay=False,
                ready=True,
                zone_supervision_trouble=False,
                zone_fire_loop_trouble=False,
                zone_low_battery_trouble=False,
                zone_tamper_trouble=False,
                voice_arming=False,
                auto_arming_engaged=False,
                fire_delay_in_progress=False,
                intellizone_engage=False,
                time_to_refresh_zone_status=False,
                panic_alarm=False,
                police_code_delay=False,
                follow_become_delay=False,
                remote_arming=False,
                stay_arming_auto=False,
                partition_recently_close=False,
                cancel_alarm_reporting_on_disarming=False,
                tx_delay_finished=False,
                auto_arm_reach=False,
                fire_delay_end=False,
                no_movement_delay_end=False,
                alarm_duration_finished=False,
                entry_delay_finished=False,
                exit_delay_finished=False,
                intellizone_delay_finished=False,
                all_zone_closed=True, inhibit_ready=True,
                bypass_ready=True, force_ready=True,
                stay_instant_ready=True)
    },
    'panel_status': dict(installer_lock_active=False),
    '_recycle_system': [58, 11, 0, 0, 0, 0, 0, 0],
    'arm_disarm_report_delay_timer': 0,
    '_free': None,
    'bus-module_trouble': {1: False, 2: False},
    'system': {
        'troubles': dict(system_trouble=False, dialer_trouble=False, module_trouble=False, bus_com_trouble=False,
                         zone_tamper_trouble=False, zone_low_battery_trouble=False, zone_fault_trouble=False,
                         time_lost_trouble=False, ac_trouble=False, battery_failure_trouble=False,
                         aux_limit_trouble=False,
                         bell_limit_trouble=False, bell_absent_trouble=False, rom_error_trouble=False,
                         tlm_trouble=False,
                         fail_tel_1_trouble=False, fail_tel_2_trouble=False, fail_tel_3_trouble=False,
                         fail_tel_4_trouble=False, com_pc_trouble=False, module_tamper_trouble=False,
                         module_rom_error_trouble=False, module_tlm_trouble=False, module_fail_to_com_trouble=False,
                         module_printer_trouble=False, module_ac_trouble=False, module_battery_fail=False,
                         module_aux_trouble=False, missing_keypad_trouble=False, missing_module_trouble=False,
                         safety_mismatch_trouble=False, bus_global_fail=False, bus_overload_trouble=False,
                         mdl_com_error=False),
        'report': {'arm_disarm_delay_timer': 0},
        'power': {'battery': 13.4, 'dc': 13.5, 'vdc': 16.5},
        'panel_status': {'installer_lock_active': False},
        'event': {'_event_pointer': 13312, '_event_pointer_bus': 41741},
        'date': {'time': datetime.datetime(2019, 10, 11, 21, 12, 2), 'weekday': 6}
    }
}


def test_convert_raw_status(mocker):
    mocker.patch.object(ps, 'sendChange')
    mocker.patch.object(ps, 'sendEvent')
    connection = mocker.stub(name='Connection_stub')
    p = Paradox(connection)
    status = convert_raw_status(evo_status)

    assert status["zone"] == {
        1: dict(open=False, tamper=False, low_battery=False, generated_alarm=False, presently_in_alarm=False,
                activated_entry_delay=False,
                activated_intellizone_delay=False, bypassed=False, shutted_down=False,
                tx_delay=False, supervision_trouble=False),
        2: dict(open=False, tamper=False, low_battery=False, generated_alarm=False,
                presently_in_alarm=False,
                activated_entry_delay=False,
                activated_intellizone_delay=False,
                bypassed=False,
                shutted_down=False,
                tx_delay=False,
                supervision_trouble=False)
    }
    assert status["partition"] == evo_status["partition_status"]
    assert status["door"] == {1: dict(open=False), 2: dict(open=False)}
    assert status["bus-module"] == {1: dict(trouble=False), 2: dict(trouble=False)}
    assert status["system"]["power"] == {
        "vdc": 16.5,
        "battery": 13.4,
        "dc": 13.5
    }
    assert status["system"]["date"] == {
        'time': datetime.datetime(2019, 10, 11, 21, 12, 2),
        'weekday': 6
    }
    assert status["system"]["troubles"] == evo_status["system"]["troubles"]
    # TODO: Think out a PGM format
