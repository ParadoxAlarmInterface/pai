"""Explicit composition of supported products and discovery protocols.

Imported on first discovery/decoder construction, not when importing Panel.
New drivers register here; neither the coordinator nor other families change.
"""

from . import digiplex, evo, mg6250, spectra_magellan
from .binary import BinaryPanel
from .prt3.panel import PRT3Panel

PRODUCTS = {
    **evo.PRODUCTS,
    **spectra_magellan.PRODUCTS,
    **mg6250.PRODUCTS,
    **digiplex.PRODUCTS,
}

DISCOVERY = {
    "binary": (BinaryPanel.detect, digiplex.PanelDGP848.detect),
    "prt3": (PRT3Panel.detect,),
}
