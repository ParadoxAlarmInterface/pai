from .panel import Panel


def create_panel(core, product_id=None) -> Panel:
    if product_id is None:
        return Panel(core, product_id, True)
    elif product_id == 'DIGIPLEX_EVO_48':
        from . import evo
        return evo.Panel_EVO48(core, product_id, True)
    elif product_id == 'DIGIPLEX_EVO_96':
        from . import evo
        return evo.Panel_EVO96(core, product_id, True)
    elif product_id == 'DIGIPLEX_EVO_192':
        from . import evo
        return evo.Panel_EVO192(core, product_id, True)
    elif product_id == 'DIGIPLEX_EVO_HD':
        from . import evo
        return evo.Panel_EVOHD(core, product_id, True)
    elif product_id in [
        'SPECTRA_SP4000', 'SPECTRA_SP5500', 'SPECTRA_SP6000', 'SPECTRA_SP7000',
        'SPECTRA_SP65',
        'MAGELLAN_MG5000', 'MAGELLAN_MG5050'
    ]:
        from . import spectra_magellan
        return spectra_magellan.Panel(core, product_id, False)
    else:
        raise NotImplementedError(
            "We are not sure what panel you have (product_id: {}). Please create an issue. Maybe we can help you.".format(str(product_id)))

