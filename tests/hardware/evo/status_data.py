import datetime

message_parser_output = {
    '_weekday': 5,
    'pgm_flags': dict(
        chime_zone_partition={1: False, 2: False},  # 1-4
        power_smoke=False,
        ground_start=False, kiss_off=False, line_ring=False,
        bell_partition={1: False, 2: False},  # 1-8
        fire_alarm={1: False, 2: False},  # 1-8
        open_close_kiss_off={1: False, 2: False}  # 1-8
    ),
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
                alarm_in_memory=False, trouble=False, entry_delay=False, exit_delay=False, ready=True,
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
                alarm_in_memory=False, trouble=False,
                entry_delay=False, exit_delay=False,
                ready=False,
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
    '_recycle_system': [58, 11, 0, 0, 0, 0, 0, 0],
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
        'power': {'battery': 13.7, 'dc': 13.9, 'vdc': 16.7},
        'panel_status': {'installer_lock_active': False},
        'event': {'_event_pointer': 13312, '_event_pointer_bus': 41741},
        'date': {'time': datetime.datetime(2019, 10, 16, 15, 6, 22), 'weekday': 4}
    }
}

converted_status = {
    'pgm': {
        'chime_zone_partition': {
            1: {'chime_zone_partition': False},
            2: {'chime_zone_partition': False}
        },
        'power_smoke': False,
        'ground_start': False,
        'kiss_off': False,
        'line_ring': False,
        'bell_partition': {
            1: {'bell_partition': False},
            2: {'bell_partition': False}
        },
        'fire_alarm': {
            1: {'fire_alarm': False},
            2: {'fire_alarm': False}
        },
        'open_close_kiss_off': {
            1: {'open_close_kiss_off': False},
            2: {'open_close_kiss_off': False}
        }
    },
    'key-switch': {
        1: {'triggered': False}, 2: {'triggered': False}
    },
    'door': {1: {'open': False}, 2: {'open': False}},
    'system': {
        'troubles': {
            'system_trouble': False, 'dialer_trouble': False, 'module_trouble': False,
            'bus_com_trouble': False,
            'zone_tamper_trouble': False, 'zone_low_battery_trouble': False, 'zone_fault_trouble': False,
            'time_lost_trouble': False, 'ac_trouble': False, 'battery_failure_trouble': False,
            'aux_limit_trouble': False, 'bell_limit_trouble': False, 'bell_absent_trouble': False,
            'rom_error_trouble': False, 'tlm_trouble': False, 'fail_tel_1_trouble': False,
            'fail_tel_2_trouble': False, 'fail_tel_3_trouble': False, 'fail_tel_4_trouble': False,
            'com_pc_trouble': False, 'module_tamper_trouble': False, 'module_rom_error_trouble': False,
            'module_tlm_trouble': False, 'module_fail_to_com_trouble': False, 'module_printer_trouble': False,
            'module_ac_trouble': False, 'module_battery_fail': False, 'module_aux_trouble': False,
            'missing_keypad_trouble': False, 'missing_module_trouble': False, 'safety_mismatch_trouble': False,
            'bus_global_fail': False, 'bus_overload_trouble': False, 'mdl_com_error': False
        },
        'date': {'weekday': 4, 'time': datetime.datetime(2019, 10, 16, 15, 6, 22)},
        'power': {'vdc': 16.7, 'battery': 13.7, 'dc': 13.9},
        'panel_status': {'installer_lock_active': False},
        'event': {},
        'report': {'arm_disarm_delay_timer': 0}
    },
    'zone': {
        1: {'open': False, 'tamper': False, 'low_battery': False, 'generated_alarm': False, 'presently_in_alarm': False,
            'activated_entry_delay': False, 'activated_intellizone_delay': False, 'bypassed': False,
            'shutted_down': False,
            'tx_delay': False, 'supervision_trouble': False},
        2: {'open': False, 'tamper': False, 'low_battery': False, 'generated_alarm': False, 'presently_in_alarm': False,
            'activated_entry_delay': False, 'activated_intellizone_delay': False, 'bypassed': False,
            'shutted_down': False,
            'tx_delay': False, 'supervision_trouble': False}
    },
    'partition': {
        1: {'fire_alarm': False, 'audible_alarm': False, 'silent_alarm': False, 'was_in_alarm': False,
            'arm_no_entry': False, 'arm_stay': False, 'arm_away': False, 'arm': False, 'lockout': False,
            'programming': False, 'zone_bypassed': False, 'alarm_in_memory': False, 'trouble': False,
            'entry_delay': False,
            'exit_delay': False, 'ready': True, 'zone_supervision_trouble': False, 'zone_fire_loop_trouble': False,
            'zone_low_battery_trouble': False, 'zone_tamper_trouble': False, 'voice_arming': False,
            'auto_arming_engaged': False, 'fire_delay_in_progress': False, 'intellizone_engage': False,
            'time_to_refresh_zone_status': False, 'panic_alarm': False, 'police_code_delay': False,
            'follow_become_delay': False, 'remote_arming': False, 'stay_arming_auto': False,
            'partition_recently_close': False, 'cancel_alarm_reporting_on_disarming': False, 'tx_delay_finished': False,
            'auto_arm_reach': False, 'fire_delay_end': False, 'no_movement_delay_end': False,
            'alarm_duration_finished': False, 'entry_delay_finished': False, 'exit_delay_finished': False,
            'intellizone_delay_finished': False, 'all_zone_closed': True, 'inhibit_ready': True, 'bypass_ready': True,
            'force_ready': True, 'stay_instant_ready': True},
        2: {'fire_alarm': False, 'audible_alarm': False, 'silent_alarm': False, 'was_in_alarm': False,
            'arm_no_entry': False, 'arm_stay': False, 'arm_away': False, 'arm': False, 'lockout': False,
            'programming': False, 'zone_bypassed': False, 'alarm_in_memory': False, 'trouble': False,
            'entry_delay': False,
            'exit_delay': False, 'ready': False, 'zone_supervision_trouble': False, 'zone_fire_loop_trouble': False,
            'zone_low_battery_trouble': False, 'zone_tamper_trouble': False, 'voice_arming': False,
            'auto_arming_engaged': False, 'fire_delay_in_progress': False, 'intellizone_engage': False,
            'time_to_refresh_zone_status': False, 'panic_alarm': False, 'police_code_delay': False,
            'follow_become_delay': False, 'remote_arming': False, 'stay_arming_auto': False,
            'partition_recently_close': False, 'cancel_alarm_reporting_on_disarming': False, 'tx_delay_finished': False,
            'auto_arm_reach': False, 'fire_delay_end': False, 'no_movement_delay_end': False,
            'alarm_duration_finished': False, 'entry_delay_finished': False, 'exit_delay_finished': False,
            'intellizone_delay_finished': False, 'all_zone_closed': True, 'inhibit_ready': True, 'bypass_ready': True,
            'force_ready': True, 'stay_instant_ready': True}
    },
    'bus-module': {1: {'trouble': False}, 2: {'trouble': False}}
}