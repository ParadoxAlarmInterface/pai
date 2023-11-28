from construct import Container

from .panel import Panel


def create_panel(core, start_communication_response: Container = None) -> Panel:
    product_id = (
        start_communication_response.fields.value.product_id
        if start_communication_response
        else None
    )
    if product_id is None:
        return Panel(core, True)
    elif product_id == "DIGIPLEX_EVO_48":
        from . import evo

        return evo.Panel_EVO48(core, start_communication_response, True)
    elif product_id == "DIGIPLEX_EVO_96":
        from . import evo

        return evo.Panel_EVO96(core, start_communication_response, True)
    elif product_id == "DIGIPLEX_EVO_192":
        from . import evo

        return evo.Panel_EVO192(core, start_communication_response, True)
    elif product_id in ["DIGIPLEX_EVO_HD", "DIGIPLEX_EVO_HD_PLUS"]:
        from . import evo

        return evo.Panel_EVOHD(core, start_communication_response, True)
    elif product_id in [
        "SPECTRA_SP4000",
        "SPECTRA_SP5500",
        "SPECTRA_SP550_PLUS",
        "SPECTRA_SP6000",
        "SPECTRA_SP7000",
        "SPECTRA_SP65",
        "SPECTRA_SP6000_PLUS",
        "SPECTRA_SP7000_PLUS",
        "MAGELLAN_MG5000",
        "MAGELLAN_MG5050",
        "MAGELLAN_MG5050_PLUS",
        "MAGELLAN_MG5075",
    ]:
        from . import spectra_magellan

        return spectra_magellan.Panel(core, start_communication_response, False)
    else:
        raise NotImplementedError(
            "We are not sure what panel you have (product_id: {}). \
            Please create an issue. Maybe we can help you.".format(
                str(product_id)
            )
        )
