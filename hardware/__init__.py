from .panel import Panel
from . import evo
from . import spectra_magellan

def create_panel(core, product_id = None):
  if product_id is None:
    return Panel(core)
  elif product_id in ['DIGIPLEX_EVO_48', 'DIGIPLEX_EVO_96', 'DIGIPLEX_EVO_192']:
    return evo.Panel(core)
  else:
    return spectra_magellan.Panel(core)