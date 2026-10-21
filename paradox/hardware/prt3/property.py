"""
PRT3 property map.

Re-exports property_map from spectra_magellan unchanged.

The property names used by PRT3 status replies (open, alarm, trouble,
arm, arm_stay, arm_force, exit_delay, entry_delay, …) are identical to
those used by the Spectra/Magellan binary panels.  There is no need for
a separate map — re-exporting keeps the two in sync automatically.
"""

from paradox.hardware.spectra_magellan.property import property_map  # noqa: F401
