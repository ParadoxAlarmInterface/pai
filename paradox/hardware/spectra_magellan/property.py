from paradox.event import EventLevel


property_map = {
	'timer_loss_trouble': dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Timer lost trouble", False="Timer recovered")),
	"fire_loop_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Fire loop", False="Fire loop recovered")),
    "module_tamper_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Module tampered", False="Module tamper cleared"))
    "zone_tamper_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Zone tampered", False="Zone tamper cleared")),
    "communication_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Communication trouble", False="Communication OK"))
    "bell_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Bell trouble", False="Bell OK")),
    "power_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Power trouble", False="Power restored")),
    "rf_low_battery_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="RF Low battery trouble", False="RF battery OK")),
    "rf_interference_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="RF Interference trouble", False="RF Interference cleared")),
    "module_supervision_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Bell trouble", False="Bell OK")),
    "zone_supervision_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Zone supervision trouble", False="Zone supervision OK")),
    "wireless_repeater_battery_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Wireless repeater battery low", False="Wireless repeater battery OK")),
    "wireless_repeater_ac_loss_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Wireless reapeater lost AC Power", False="Wireless repeater AC Power restored")),
    "wireless_keypad_battery_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Wireless keypad battery low", False="Wireless keypad battery OK")),
    "wireless_keypad_ac_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Wireless keypad lost AC Power", False="Wireless keypad AC Power restored")),
    "auxiliary_output_overload_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Auxiliary output overloaded", False="Auxiliary output load OK")),
    "ac_failure_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="AC Power failure", False="AC Power restored")),
    "low_battery_trouble": dict(level=EventLevel.CRITICAL, type='system', 
		message=dict(True="Battery is low", False="Battery level is OK"))

    # "bell_output_overload_trouble" / Flag,
    # "bell_output_disconnected_trouble" / Flag,
    # "_not_used3" / BitsInteger(2),
    # "computer_fail_to_communicate_trouble" / Flag,
    # "voice_fail_to_communicate_trouble" / Flag,
    # "pager_fail_to_communicate_trouble" / Flag,
    # "central_2_reporting_ftc_indicator_trouble" / Flag,
    # "central_1_reporting_ftc_indicator_trouble" / Flag,
    # "telephone_line" / Flag),





}
