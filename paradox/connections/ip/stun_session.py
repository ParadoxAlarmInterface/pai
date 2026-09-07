import asyncio
import binascii
import json
import logging
import time

import requests

from paradox.exceptions import ConnectToSiteFailed, StunSessionRefreshFailed
from paradox.lib import stun
from paradox.lib.utils import mask_email, mask_secret

logger = logging.getLogger("PAI").getChild(__name__)

#: TURN allocations are handed out with a 600 s lifetime; renew with headroom.
SESSION_REFRESH_INTERVAL = 500

#: Bound on the SWAN site lookup. Without one a stalled HTTP call hangs the
#: connect path forever.
SITE_INFO_HTTP_TIMEOUT = 20

SENSITIVE_SITE_INFO_KEYS = {
    "panelSerial": mask_secret,
    "email": mask_email,
}


def redact_site_info(value):
    """Recursively mask serials and emails in the SWAN site listing."""
    if isinstance(value, dict):
        return {
            k: (
                SENSITIVE_SITE_INFO_KEYS[k](v)
                if k in SENSITIVE_SITE_INFO_KEYS
                else redact_site_info(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_site_info(v) for v in value]
    return value


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
        logger.info("Connecting to Site: %s", self.site_id)
        if self.site_info is None:
            self.site_info = await self._get_site_info(
                siteid=self.site_id, email=self.email
            )

        if self.site_info is None:
            raise ConnectToSiteFailed("Unable to get site info")

        logger.debug(
            "Site Info: %s", json.dumps(redact_site_info(self.site_info), indent=4)
        )
        self.module = self._select_module()

        if self.module is None:
            self.site_info = None  # Reset state
            raise ConnectToSiteFailed("Unable to find module with desired panel serial")

        xoraddr = binascii.unhexlify(self.module["xoraddr"])

        await self._stun_tcp_change_request()
        await self._stun_tcp_binding_request()
        stun_r = await self._stun_connect(xoraddr)

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

        logger.info("Connected to Site: %s", self.site_id)

    async def _stun_connect(self, xoraddr):
        logger.debug("STUN Connect Request")
        self.stun_control.send_connect_request(xoraddr=xoraddr)
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN Connect Request error: {stun.get_error(stun_r)}"
            )
        return stun_r

    async def _stun_tcp_binding_request(self):
        logger.debug("STUN TCP Binding Request")
        self.stun_control.send_binding_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Binding Request error: {stun.get_error(stun_r)}"
            )

    async def _stun_tcp_change_request(self):
        stun_host = "turn.paradoxmyhome.com"
        logger.debug("STUN TCP Change Request")
        self.stun_control = stun.StunClient(stun_host)
        self.stun_control.send_tcp_change_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise ConnectToSiteFailed(
                f"STUN TCP Change Request error: {stun.get_error(stun_r)}"
            )

    def _select_module(self):
        for site in self.site_info["site"]:
            for module in site["module"]:
                if module.get("xoraddr") is None:
                    continue

                logger.debug(
                    "Found module with panel serial: %s",
                    mask_secret(module["panelSerial"]),
                )

                if not self.panel_serial:  # Pick first available
                    return module
                elif module["panelSerial"] == self.panel_serial:
                    return module

    def get_socket(self):
        return self.stun_tunnel.sock

    def refresh_required(self) -> bool:
        """Whether the TURN allocation is close enough to expiry to renew."""
        if self.site_info is None or self.connection_timestamp == 0:
            return False

        return time.time() - self.connection_timestamp >= SESSION_REFRESH_INTERVAL

    def refresh_session(self) -> None:
        """Renew the TURN allocation.

        Blocking: this talks to the control socket synchronously. Call it from
        an executor, never from the event loop -- it used to run inline in
        ``write()``, where a slow or half-dead TURN server stalled every
        interface PAI was running until the socket gave up.
        """
        logger.info("STUN Session Refresh")
        self.stun_control.send_refresh_request()
        stun_r = self.stun_control.receive_response()
        if stun.is_error(stun_r):
            raise StunSessionRefreshFailed(
                f"STUN Session Refresh failed: {stun.get_error(stun_r)}"
            )

        self.connection_timestamp = time.time()

    def refresh_session_if_required(self) -> None:
        """Blocking refresh-if-due. Retained for callers outside the event loop."""
        if self.refresh_required():
            self.refresh_session()

    def close(self):
        self.site_info = None
        self.module = None

        if self.stun_control:
            self.stun_control.close()
            self.stun_control = None
        if self.stun_tunnel:
            self.stun_tunnel.close()
            self.stun_tunnel = None

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
        loop = asyncio.get_running_loop()
        while tries > 0:
            req = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    URL,
                    headers=headers,
                    params={"email": email, "name": siteid},
                    timeout=SITE_INFO_HTTP_TIMEOUT,
                ),
            )
            if req.status_code == 200:
                return req.json()

            logger.warning("Unable to get site info. Retrying...")
            tries -= 1
            # await, not time.sleep: this is a coroutine, and blocking here
            # stalled the whole event loop for up to 25 s.
            await asyncio.sleep(5)

        return None

    def get_potential_modules(self):
        pass
