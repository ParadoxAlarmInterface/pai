import asyncio
from binascii import hexlify
import logging

from construct import Container

from paradox.config import config as cfg
from paradox.data.model import DetectedPanel
from paradox.exceptions import PanelNotDetected
from paradox.lib.utils import describe_connection

from .panel import Panel

logger = logging.getLogger("PAI").getChild(__name__)

SPECTRA_MAGELLAN_PRODUCTS = (
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


def _driver(product_id):
    """(panel class, variable_message_length) for a product, None if unknown."""
    if product_id == "DIGIPLEX_EVO_48":
        from . import evo

        return evo.Panel_EVO48, True
    if product_id == "DIGIPLEX_EVO_96":
        from . import evo

        return evo.Panel_EVO96, True
    if product_id == "DIGIPLEX_EVO_192":
        from . import evo

        return evo.Panel_EVO192, True
    if product_id in ("DIGIPLEX_EVO_HD", "DIGIPLEX_EVO_HD_PLUS"):
        from . import evo

        return evo.Panel_EVOHD, True
    if product_id in SPECTRA_MAGELLAN_PRODUCTS:
        from . import spectra_magellan

        return spectra_magellan.Panel, False
    if product_id == "MAGELLAN_MG6250":
        from . import mg6250

        return mg6250.Panel, False
    if product_id in ("DIGIPLEX_v13", "DIGIPLEX_v2", "DIGIPLEX_NE"):
        # One driver for the family; it only reads the memory range captured on
        # a DGP-848 (zones 1-48, partitions 1-2) and warns on DGP-NE96.
        from . import digiplex

        return digiplex.PanelDGP848, False
    return None


def create_panel(core, start_communication_response: Container = None) -> Panel:
    product_id = (
        start_communication_response.fields.value.product_id
        if start_communication_response
        else None
    )
    if product_id is None:
        return Panel(core, True)
    driver = _driver(product_id)
    if driver is None:
        raise NotImplementedError(
            "We are not sure what panel you have (product_id: {}). \
            Please create an issue. Maybe we can help you.".format(str(product_id))
        )
    cls, variable_message_length = driver
    return cls(core, start_communication_response, variable_message_length)


async def detect_panel(core) -> tuple[Panel, DetectedPanel]:
    """Identify the panel and install its driver on ``core``.

    Returns the installed driver and the identity to publish once logged in.
    Families with their own discovery implement ``Panel.detect``.
    """
    if cfg.CONNECTION_TYPE == "PRT3":
        from .prt3.panel import PRT3Panel

        return await PRT3Panel.detect(core)

    bootstrap = create_panel(core)
    core.install_panel(bootstrap)
    try:
        initiate_reply = await core.send_wait(
            bootstrap.get_message("InitiateCommunication"),
            None,
            reply_expected=0x7,
        )
    except asyncio.TimeoutError:
        # Digiplex (DGP-48/848/NE96) panels do not implement
        # InitiateCommunication (0x72) at all (issue #257).
        from .digiplex import PanelDGP848

        return await PanelDGP848.detect(core)

    if not initiate_reply:
        raise ConnectionError("Panel did not replied to InitiateCommunication")

    value = initiate_reply.fields.value
    identity = DetectedPanel(
        product_id=None,
        model=value.label.strip(b"\0 ").decode(cfg.LABEL_ENCODING),
        firmware_version="{}.{} build {}".format(
            value.application.version,
            value.application.revision,
            value.application.build,
        ),
        serial_number=hexlify(value.serial_number).decode(),
    )
    logger.info(
        "Connected via %s to %s version %s",
        describe_connection(),
        identity.model,
        identity.firmware_version,
    )

    await core.connection.on_initiate_communication(
        initiate_reply,
        lambda message, check: core.send_wait(message=message, reply_expected=check),
    )

    driver = _driver(value.get("product_id"))
    start_class = driver[0] if driver else Panel
    reply = await start_class.start_communication(core, initiate_reply)
    if reply.fields.value.product_id is None:
        raise PanelNotDetected("Failed to detect panel")

    panel = create_panel(core, reply)
    core.install_panel(panel)
    return panel, identity._replace(product_id=reply.fields.value.product_id)
