from .models.evo48 import Panel_EVO48
from .models.evo96 import Panel_EVO96
from .models.evo192 import Panel_EVO192
from .models.evohd import Panel_EVOHD

__all__ = ["Panel_EVO48", "Panel_EVO96", "Panel_EVO192", "Panel_EVOHD"]

PRODUCTS = {
    "DIGIPLEX_EVO_48": (Panel_EVO48, True),
    "DIGIPLEX_EVO_96": (Panel_EVO96, True),
    "DIGIPLEX_EVO_192": (Panel_EVO192, True),
    "DIGIPLEX_EVO_HD": (Panel_EVOHD, True),
    "DIGIPLEX_EVO_HD_PLUS": (Panel_EVOHD, True),
}
