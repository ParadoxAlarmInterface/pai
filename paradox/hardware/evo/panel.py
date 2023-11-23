import binascii
import inspect
import logging
import typing

from construct import ChecksumError, Construct, Container, MappingError

from paradox.config import config as cfg
from paradox.exceptions import AuthenticationFailed, StatusRequestException

from . import parsers
from ..panel import Panel as PanelBase
from .event import event_map
from .property import property_map

logger = logging.getLogger("PAI").getChild(__name__)

ZONE_ACTIONS = dict(
    bypass={
        "flags": {"bypassed": True},
        "operation": "set",
    },
    clear_bypass={
        "flags": {"bypassed": True},
        "operation": "clear",
    },
    clear_alarm_memory={
        "flags": {"generated_alarm": True},
        "operation": "clear",
    },
)


class Panel_EVOBase(PanelBase):
    event_map = event_map
    property_map = property_map
    max_eeprom_response_data_length = 64
    status_request_addresses = parsers.RAMDataParserMap.keys()

    def __init__(
        self, core, start_communication_response, variable_message_length=True
    ):
        super().__init__(core, variable_message_length)

        self._populate_settings(start_communication_response)

    def _populate_settings(self, start_communication_response):
        raw_data = (
            start_communication_response.fields.data
            + start_communication_response.checksum
        )
        parsed = parsers.InitializeCommunication.parse(raw_data)
        if cfg.LOGGING_DUMP_MESSAGES:
            logger.debug("Second parse of InitializeCommunication response: %s", parsed)
        self.settings = parsed.fields.value

    def get_message(self, name: str) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(parsers))
            if name in clsmembers:
                return clsmembers[name]
        except ResourceWarning:
            pass

        return super().get_message(name)

    async def dump_memory(self, file, memory_type):
        """
        Dumps EEPROM and RAM memory to files
        :return:
        """
        if memory_type == "ram":
            await self.dump_memory_to_file(file, range(0, 59), True)
        elif memory_type == "eeprom":
            await self.dump_memory_to_file(file, range(0, 0xFFFF, 64))
        else:
            raise AttributeError(f"Unknown memory type: {memory_type}")

    async def dump_memory_to_file(self, file, range_, ram=False):
        mem_type = "RAM" if ram else "EEPROM"
        logger.info("Dump " + mem_type)

        def expect(command, address):
            return (
                lambda m: m.fields.value.po.command == command
                and m.fields.value.address == address
            )

        packet_length = 64  # 64 is max
        for address in range_:
            args = dict(
                address=address, length=packet_length, control=dict(ram_access=ram)
            )
            logger.info("Dumping %s: address %d" % (mem_type, address))
            reply = await self.core.send_wait(
                parsers.ReadEEPROM,
                args,
                reply_expected=expect(0x5, address),
            )

            if reply is None:
                logger.error("Could not read %s: address %d" % (mem_type, address))
                return

            data = reply.fields.value.data

            file.write(data)

    def parse_message(
        self, message: bytes, direction="topanel"
    ) -> typing.Optional[Container]:
        try:
            if message is None or len(message) == 0:
                return None

            parent_parsed = super().parse_message(message, direction)
            if parent_parsed:
                return parent_parsed

            if direction == "topanel":
                if message[0] == 0x70:
                    return parsers.CloseConnection.parse(message)
                elif message[0] == 0x00:
                    return parsers.InitializeCommunication.parse(message)
                elif message[0] == 0x30:
                    return parsers.SetTimeDate.parse(message)
                elif message[0] == 0x40:
                    return parsers.PerformPartitionAction.parse(message)
                elif message[0] == 0xD0:
                    return parsers.PerformZoneAction.parse(message)
            else:
                if message[0] >> 4 == 0x7:
                    return parsers.ErrorMessage.parse(message)
                elif message[0] >> 4 == 0x1:
                    return parsers.LoginConfirmationResponse.parse(message)
                elif message[0] >> 4 == 0x3:
                    return parsers.SetTimeDateResponse.parse(message)
                elif message[0] >> 4 == 4:  # Used for partitions and PGMs
                    return parsers.PerformActionResponse.parse(message)
                elif message[0] >> 4 == 0xD:
                    return parsers.PerformZoneActionResponse.parse(message)
                # elif message[0] == 0x50 and message[2] == 0x80:
                #     return PanelStatus.parse(message)
                # elif message[0] == 0x50 and message[2] < 0x80:
                #     return ReadEEPROM.parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                #     return PanelStatusResponse[message[3]].parse(message)
                # elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                elif message[0] >> 4 == 0x5:
                    return parsers.ReadEEPROMResponse.parse(message)
                # elif message[0] == 0x60 and message[2] < 0x80:
                #     return WriteEEPROM.parse(message)
                # elif message[0] >> 4 == 0x06 and message[2] < 0x80:
                #     return WriteEEPROMResponse.parse(message)
                elif message[0] >> 4 == 0xE:
                    if message[1] == 0xFF:
                        return parsers.LiveEvent.parse(message)
                    else:
                        return parsers.RequestedEvent.parse(message)

        except ChecksumError as e:
            logger.error("ChecksumError %s, message: %s", e, binascii.hexlify(message))
        except Exception:
            logger.exception("Exception parsing message: %s", binascii.hexlify(message))

        return None

    async def initialize_communication(self, password) -> bool:
        encoded_password = self.encode_password(password)

        self.settings.pc_password = encoded_password
        payload = parsers.InitializeCommunication.build(
            dict(fields=dict(value=self.settings))
        )

        logger.info("Installer login")
        reply = await self.core.send_wait(message=payload, reply_expected=[0x1, 0x0])

        if reply is None:
            logger.error("Installer login failed")
            return False

        if reply.fields.value.po.command == 0x0:
            logger.error(
                "Authentication Failed. Wrong PASSWORD. Make sure you use correct PC Password. In Babyware: "
                "Right click on your panel -> Properties -> PC Communication (Babyware) -> PC Communication "
                "(Babyware) Tab."
            )
            raise AuthenticationFailed("Wrong PASSWORD")

        if reply.fields.value.po.command == 0x1:
            logger.info("Authentication Success")

            if not reply.fields.value.po.status.Winload_connected:
                logger.warning("Winload_connected is still False")

            return True

        logger.error("Invalid response to InitializeCommunication: %s", reply)
        return False

    @staticmethod
    def _request_status_reply_check(message: Container, address: int):
        mvars = message.fields.value

        if (
            mvars.po.command == 0x5
            and mvars.control.ram_access is True
            and mvars.bus_address == 0x00  # panel
            and mvars.address == address
        ):
            return True

        return False

    async def request_status(self, i: int) -> typing.Optional[Container]:
        args = dict(address=i, length=64, control=dict(ram_access=True))
        reply = await self.core.send_wait(
            parsers.ReadEEPROM,
            args,
            reply_expected=lambda m: self._request_status_reply_check(
                m, args["address"]
            ),
        )
        if reply is not None:
            logger.debug("Received status response: %d" % i)
            return self.handle_status(reply, parsers.RAMDataParserMap)
        else:
            raise StatusRequestException("No reply to status request: %d" % i)

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """
        Control Partitions
        :param list partitions: a list of partitions
        :param str command: textual command
        :return: True if we have at least one success
        """
        args = dict(partitions={i: command for i in partitions})

        try:
            reply = await self.core.send_wait(
                parsers.PerformPartitionAction, args, reply_expected=0x4
            )
        except MappingError:
            logger.error('Partition command: "%s" is not supported' % command)
            return False

        if reply:
            logger.info('Partition command: "%s" succeeded' % command)
        else:
            logger.info('Partition command: "%s" failed' % command)
        return reply is not None

    async def control_zones(self, zones: list, command: str) -> bool:
        """
        Control zones
        :param list zones: a list of zones
        :param str command: textual command
        :return: True if we have at least one success
        """
        if command not in ZONE_ACTIONS:
            return False

        args = ZONE_ACTIONS[command].copy()
        args["zones"] = zones

        try:
            reply = await self.core.send_wait(
                parsers.PerformZoneAction, args, reply_expected=0xD
            )
        except MappingError:
            logger.error('Zone command: "%s" is not supported' % command)
            return False

        if reply:
            logger.info('Zone command: "%s" succeeded' % command)
        else:
            logger.info('Zone command: "%s" failed' % command)
        return reply is not None

    async def control_outputs(self, outputs, command) -> bool:
        """
        Control PGM
        :param list outputs: a list of pgms
        :param str command: textual command
        :return: True if we have at least one success
        """

        args = {"pgms": outputs, "command": command}

        try:
            reply = await self.core.send_wait(
                parsers.PerformPGMAction, args, reply_expected=0x4
            )
        except MappingError:
            logger.error('PGM command: "%s" is not supported' % command)
            return False

        if reply:
            logger.info('PGM command: "%s" succeeded' % command)
        else:
            logger.info('PGM command: "%s" failed' % command)
        return reply is not None

    async def control_doors(self, doors, command) -> bool:
        """
        Control Doors
        :param list doors: a list of doors
        :param str command: textual command
        :return: True if we have at least one success
        """

        args = {"doors": doors, "command": command}

        try:
            reply = await self.core.send_wait(
                parsers.PerformDoorAction, args, reply_expected=0x4
            )
        except MappingError:
            logger.error('Door command: "%s" is not supported' % command)
            return False

        if reply:
            logger.info('Door command: "%s" succeeded' % command)
        else:
            logger.info('Door command: "%s" failed' % command)
        return reply is not None

    async def send_panic(self, partitions, panic_type, user_id):
        accepted = False

        args = {"partitions": partitions, "panic_type": panic_type, "user_id": user_id}

        reply = await self.core.send_wait(
            parsers.SendPanicAction, args, reply_expected=0x4
        )

        if reply is not None:
            accepted = True

        return accepted
