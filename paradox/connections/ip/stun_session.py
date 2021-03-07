import asyncio
import binascii
import json
import logging
import time

import requests

from paradox.exceptions import ConnectToSiteFailed, StunSessionRefreshFailed
from paradox.lib import stun

logger = logging.getLogger("PAI").getChild(__name__)


class StunSession:
    def __init__(self, site_id, email, panel_serial):
        self.site_id = site_id
        self.email = email
        self.panel_serial = panel_serial

        self.site_info = None
        self.module = None
        self.stun_control = None
        self.stun_tunnel = None

        self.connection_timestamp = 0

    async def connect(self) -> None:
        self.connection_timestamp = 0
        logger.info("Connecting to Site: {}".format(self.site_id))
        if self.site_info is None:
            self.site_info = await self._get_site_info(
                siteid=self.site_id, email=self.email
            )

        if self.site_info is None:
            raise ConnectToSiteFailed("Unable to get site info")

        # xoraddr = binascii.unhexlify(self.site_info['site'][0]['module'][0]['xoraddr'])
        self.module = None

        logger.debug("Site Info: {}".format(json.dumps(self.site_info, indent=4)))

        if self.panel_serial:
            for site in self.site_info["site"]:
                for module in site:
                    logger.debug(
                        "Found module with panel serial: {}".format(
                            module["panelSerial"]
                        )
                    )
                    if module["panelSerial"] == self.panel_serial:
                        self.module = module
                        break

                if self.module is not None:
                    break
        else:
            self.module = self.site_info["site"][0]["module"][0]  # Use first

        if self.module is None:
            self.site_info = None  # Reset state
            raise ConnectToSiteFailed("Unable to find module with desired panel serial")

        xoraddr = binascii.unhexlify(self.module["xoraddr"])

        stun_host = "turn.paradoxmyhome.com"

        logger.debug("STUN TCP Change Request")
        self.stun_control = stun.StunClient(stun_host)
        self.stun_control.send_tcp_change_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Change Request error: {stun.get_error(stun_r)}"
            )

        logger.debug("STUN TCP Binding Request")
        self.stun_control.send_binding_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Binding Request error: {stun.get_error(stun_r)}"
            )

        logger.debug("STUN Connect Request")
        self.stun_control.send_connect_request(xoraddr=xoraddr)
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN Connect Request error: {stun.get_error(stun_r)}"
            )

        self.connection_timestamp = time.time()

        connection_id = stun_r[0]["attr_body"]
        raddr = self.stun_control.sock.getpeername()

        logger.debug("STUN Connection Bind Request")
        self.stun_tunnel = stun.StunClient(host=raddr[0], port=raddr[1])
        self.stun_tunnel.send_connection_bind_request(binascii.unhexlify(connection_id))
        stun_r = self.stun_tunnel.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN Connection Bind Request error: {stun.get_error(stun_r)}"
            )

        logger.info("Connected to Site: {}".format(self.site_id))

    def get_socket(self):
        return self.stun_tunnel.sock

    def refresh_session_if_required(self) -> None:
        if self.site_info is None or self.connection_timestamp == 0:
            return

        # Refresh session if required
        if time.time() - self.connection_timestamp >= 500:
            logger.info("STUN Session Refresh")
            self.stun_control.send_refresh_request()
            stun_r = self.stun_control.receive_response()
            if stun.is_error(stun_r):
                self.connected = False
                raise StunSessionRefreshFailed(
                    f"STUN Session Refresh failed: {stun.get_error(stun_r)}"
                )

            self.connection_timestamp = time.time()

    def close(self):
        if self.stun_control:
            try:
                self.stun_control.close()
                self.stun_control = None
            except:
                logger.exception("stun_control socket close failed")
        if self.stun_tunnel:
            try:
                self.stun_tunnel.close()
                self.stun_tunnel = None
            except:
                logger.exception("stun_tunnel socket close failed")

        self.connection_timestamp = 0

    @staticmethod
    async def _get_site_info(email, siteid):
        logger.info("Getting site info")
        URL = "https://api.insightgoldatpmh.com/v1/site"

        headers = {
            "User-Agent": "Mozilla/3.0 (compatible; Indy Library)",
            "Accept-Encoding": "identity",
            "Accept": "text/html, */*",
        }

        tries = 5
        loop = asyncio.get_event_loop()
        while tries > 0:
            req = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    URL, headers=headers, params={"email": email, "name": siteid}
                ),
            )
            if req.status_code == 200:
                return req.json()

            logger.warning("Unable to get site info. Retrying...")
            tries -= 1
            time.sleep(5)

        return None
