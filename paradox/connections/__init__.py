import logging

from paradox.config import config as cfg, get_serial_protocol

from .connection import Connection

logger = logging.getLogger("PAI").getChild(__name__)


def create_connection() -> Connection:
    """Build the configured transport; panel discovery belongs to the driver."""
    if cfg.CONNECTION_TYPE == "Serial":
        logger.info("Using Serial Connection")
        from .serial.connection import E0FESerialCommunication, SerialCommunication

        serial_class = (
            E0FESerialCommunication
            if get_serial_protocol() == "e0fe"
            else SerialCommunication
        )
        return serial_class(port=cfg.SERIAL_PORT, baud=cfg.SERIAL_BAUD)
    if cfg.CONNECTION_TYPE == "IP":
        logger.info("Using IP Connection")
        if cfg.IP_CONNECTION_BARE:
            from .ip.connection import BareIPConnection, E0FEBareIPConnection

            bare_class = (
                E0FEBareIPConnection
                if get_serial_protocol() == "e0fe"
                else BareIPConnection
            )
            return bare_class(host=cfg.IP_CONNECTION_HOST, port=cfg.IP_CONNECTION_PORT)
        if cfg.IP_CONNECTION_SITEID and cfg.IP_CONNECTION_EMAIL:
            from .ip.connection import StunIPConnection

            return StunIPConnection(
                site_id=cfg.IP_CONNECTION_SITEID,
                email=cfg.IP_CONNECTION_EMAIL,
                panel_serial=cfg.IP_CONNECTION_PANEL_SERIAL,
                password=cfg.IP_CONNECTION_PASSWORD,
            )
        from .ip.connection import LocalIPConnection

        return LocalIPConnection(
            host=cfg.IP_CONNECTION_HOST,
            port=cfg.IP_CONNECTION_PORT,
            password=cfg.IP_CONNECTION_PASSWORD,
        )
    if cfg.CONNECTION_TYPE == "PRT3":
        logger.info("Using PRT3 Serial Connection")
        from .prt3.connection import PRT3SerialConnection

        return PRT3SerialConnection(
            port=cfg.PRT3_SERIAL_PORT, baud=cfg.PRT3_SERIAL_BAUD
        )
    raise AssertionError(f"Invalid connection type: {cfg.CONNECTION_TYPE}")
