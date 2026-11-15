from construct import Container

from paradox.data.model import DetectedPanel
from paradox.exceptions import PanelNotDetected

from .panel import Panel


def create_panel(core, start_communication_response: Container = None) -> Panel:
    """Construct a registered driver, or the binary identification decoder."""
    from .binary import BinaryPanel
    from .registry import PRODUCTS

    product_id = (
        start_communication_response.fields.value.product_id
        if start_communication_response
        else None
    )
    if product_id is None:
        return BinaryPanel(core, True)
    driver = PRODUCTS.get(product_id)
    if driver is None:
        raise NotImplementedError(
            "We are not sure what panel you have (product_id: {}). \
            Please create an issue. Maybe we can help you.".format(
                str(product_id)
            )
        )
    cls, variable_message_length = driver
    return cls(core, start_communication_response, variable_message_length)


async def detect_panel(core) -> tuple[Panel, DetectedPanel]:
    """Try the link's discovery strategies in order.

    Only an unanswered probe returns None to allow another strategy. Once a
    protocol replies, errors must propagate rather than probe another protocol.
    Each successful strategy installs its decoder before returning its identity.
    """
    from .registry import DISCOVERY

    protocol = core.connection.panel_protocol
    strategies = DISCOVERY.get(protocol)
    if strategies is None:
        raise PanelNotDetected(f"No panel discovery for protocol {protocol!r}")
    for detect in strategies:
        result = await detect(core)
        if result is not None:
            return result
    raise ConnectionError(f"No panel answered discovery for protocol {protocol!r}")
