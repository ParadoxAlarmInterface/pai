from .panel import Panel

__all__ = ["Panel"]

PRODUCTS = {
    product: (Panel, False)
    for product in (
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
    )
}
