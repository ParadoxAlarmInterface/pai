from . import evo
from . import spectra_magellan
from .panel import Panel


def create_panel(core, product_id=None) -> Panel:
    if product_id is None:
        return Panel(core, product_id)
    elif product_id == 'DIGIPLEX_EVO_48':
        return evo.Panel_EVO48(core, product_id)
    elif product_id == 'DIGIPLEX_EVO_96':
        return evo.Panel_EVO96(core, product_id)
    elif product_id == 'DIGIPLEX_EVO_192':
        return evo.Panel_EVO192(core, product_id)
    else:
        return spectra_magellan.Panel(core, product_id)
