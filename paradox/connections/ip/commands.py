import binascii
import logging

from paradox.connections.ip.parsers import (IPMessageCommand, IPMessageRequest,
                                            IPPayloadConnectResponse)
from paradox.exceptions import ConnectToIpModuleFailed, PAICriticalException

logger = logging.getLogger("PAI").getChild(__name__)


class IPModuleConnectCommand:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self):
        await self._authenticate_to_ip_module()

        await self._send_keep_alive_command()

        # # F4
        # logger.debug("Sending F4")
        # msg = binascii.unhexlify('aa00000309f400000001eeeeeeee0000')
        # self.connection.send_raw(msg)
        # message_payload = await self.wait_for_message(raw=True)
        #
        # logger.debug("F4 answer: {}".format(binascii.hexlify(message_payload)))

        await self._send_upload_download_connection_command()

        # F8
        await self._send_toggle_keep_alive_command()

        logger.info("Session successfully established with IP Module")

    async def _send_toggle_keep_alive_command(self):
        logger.debug("Sending toggle keep alive request")
        payload = binascii.unhexlify(
            "0a500080000000000000000000000000000000000000000000000000000000000000000000d0"
        )
        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    command=IPMessageCommand.toggle_keep_alive,
                    flags=dict(installer_mode=True),
                    cryptor_code="aes_256_ecb",
                ),
                payload=payload,
            ),
            password=self.connection.key,
        )
        await self.connection.send_raw_ip_message(msg)
        in_message = await self.connection.wait_for_ip_message()
        logger.debug(
            "Toggle keep alive response: {}".format(
                binascii.hexlify(in_message.payload)
            )
        )

    async def _send_upload_download_connection_command(self):
        # F3
        logger.debug("Sending upload download connection request")
        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    command=IPMessageCommand.upload_download_connection,
                    flags=dict(installer_mode=True),
                    cryptor_code="aes_256_ecb",
                )
            ),
            password=self.connection.key,
        )
        await self.connection.send_raw_ip_message(msg)
        in_message = await self.connection.wait_for_ip_message()
        logger.debug(
            "Upload download connection response: {}".format(
                binascii.hexlify(in_message.payload)
            )
        )

    async def _send_keep_alive_command(self):
        # F2
        logger.debug("Sending keep alive request")
        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    command=IPMessageCommand.keep_alive,
                    flags=dict(installer_mode=True),
                    cryptor_code="aes_256_ecb",
                ),
                payload=b"\x00\x00\x00\x00",
            ),
            password=self.connection.key,
        )
        await self.connection.send_raw_ip_message(msg)
        in_message = await self.connection.wait_for_ip_message()
        logger.debug(
            "Keep alive response: {}".format(binascii.hexlify(in_message.payload))
        )

    async def _authenticate_to_ip_module(self):
        logger.info("Authenticating with IP Module")

        self.connection.reset_key()
        msg = IPMessageRequest.build(
            dict(
                header=dict(
                    command=IPMessageCommand.connect,
                    # sub_command=3,
                    flags=dict(installer_mode=True),
                    cryptor_code="aes_256_ecb",
                ),
                payload=self.connection.key,
            ),
            password=self.connection.key,
        )
        await self.connection.send_raw_ip_message(msg)
        in_message = await self.connection.wait_for_ip_message()
        response = IPPayloadConnectResponse.parse(in_message.payload)

        if response.login_status != "success":
            logger.error(f"Error connecting to IP Module: {response.login_status}")

            if response.login_status == "invalid_password":
                raise PAICriticalException("Invalid IP Module password")
            else:
                raise ConnectToIpModuleFailed(f"Reason: {response.login_status}")

        logger.info(
            "Authentication Success. IP({}) Module version {:02x}, firmware: {}.{}, serial: {}".format(
                response.ip_type,
                response.hardware_version,
                response.ip_firmware_major,
                response.ip_firmware_minor,
                binascii.hexlify(response.ip_module_serial).decode("utf-8"),
            )
        )

        self.connection.set_key(response.key)
        self.ip_response_flags = in_message.header.flags
