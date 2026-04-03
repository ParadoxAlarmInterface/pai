#!/usr/bin/env python3
import argparse
import binascii
from collections import OrderedDict
import re
import traceback

import yaml

from paradox.connections.ip.parsers import (
    IPMessageCommand,
    IPMessageRequest,
    IPMessageResponse,
    IPMessageType,
    IPPayloadConnectResponse,
)
from paradox.connections.serial_encryption import make_serial_key
from paradox.hardware import create_panel
from paradox.hardware.parsers import Encrypted, InitiateCommunicationResponse
from paradox.lib.crypto import decrypt_serial_message


class Colors:  # You may need to change color settings
    RED = "\033[31m"
    ENDC = "\033[m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    ON_WHITE = "\033[30m\033[47m"


def ordered_load(stream, Loader=yaml.loader.SafeLoader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))

    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    return yaml.load(stream, OrderedLoader)


class PayloadParser:
    def __init__(self):
        self.panel = create_panel(None)

    def parse(self, parsed):
        try:
            message_type = parsed.header.message_type
            if message_type == IPMessageType.serial_passthrough_request:
                self._parse_message(parsed.payload, "topanel")
            elif message_type == IPMessageType.serial_passthrough_response:
                self._parse_serial_passthrough_response(parsed)
            elif message_type == IPMessageType.ip_request:
                self._parse_ip_request(parsed)
            elif message_type == IPMessageType.ip_response:
                self._parse_ip_response(parsed)
        except Exception:
            print(f"{Colors.RED}Failed to parse message: \n{parsed}{Colors.ENDC}")
            traceback.print_exc()

    def _parse_ip_response(self, parsed):
        if (
            parsed.header.command == IPMessageCommand.connect
            and parsed.header.sub_command == 0
        ):
            print(
                f"{Colors.ON_WHITE}{IPPayloadConnectResponse.parse(parsed.payload)}{Colors.ENDC}"
            )
            if len(parsed.payload) > 25:
                p = parsed.payload[25:62]
                print(
                    f"{Colors.ON_WHITE}InitiateCommunicationResponse:\n{InitiateCommunicationResponse.parse(p)}{Colors.ENDC}"
                )
        elif parsed.header.command == IPMessageCommand.multicommand:
            self._parse_multicommand(parsed, "frompanel")
        else:
            print(
                f"{Colors.RED}No parser for ip_response payload: {binascii.hexlify(parsed.payload)}{Colors.ENDC}"
            )

    def _parse_multicommand(self, parsed, direction):
        if parsed.header.sub_command == 0x0:  # Generic multicommand
            self._parse_generic_multicommand(parsed, direction)
        elif parsed.header.sub_command == 0x1:  # MGSP multiread
            self._parse_generic_mgsp_multiread(parsed, direction)
        elif parsed.header.sub_command == 0xDD:  # Unified multiread
            pass

    def _parse_serial_passthrough_response(self, parsed):
        parsed_payload = self._parse_message(parsed.payload, direction="frompanel")
        if parsed_payload is not None:
            if parsed_payload.fields.value.po.command == 0:  # panel detection
                self.panel = create_panel(None, parsed_payload)
            if parsed_payload.fields.value.po.command == 5:  # eeprom/ram read
                self._parse_serial_passthrough_eeprom_read(parsed_payload)

    def _parse_serial_passthrough_eeprom_read(self, parsed_payload):
        if (
            "control" in parsed_payload.fields.value
            and parsed_payload.fields.value.control.ram_access
            and parsed_payload.fields.value.control._eeprom_address_bits == 0
            and parsed_payload.fields.value.bus_address == 0
        ):
            ram_address = parsed_payload.fields.value.address
            ram_parser = self.panel.get_message("RAMDataParserMap").get(ram_address)
            if ram_parser is not None:
                print(
                    f"{Colors.ON_WHITE}{ram_parser.parse(parsed_payload.fields.value.data)}{Colors.ENDC}"
                )
            else:
                print(
                    f"{Colors.RED}No parser for {ram_address} ram address, data: {binascii.hexlify(parsed_payload.fields.value.data)}{Colors.ENDC}"
                )

    def _parse_ip_request(self, parsed):
        if parsed.header.command == IPMessageCommand.multicommand:
            self._parse_multicommand(parsed, "topanel")
        else:
            print(
                f"{Colors.RED}No parser for ip_request payload: {binascii.hexlify(parsed.payload)}{Colors.ENDC}"
            )

    def _parse_generic_multicommand(self, parsed, direction: str):
        i = 0
        while i < len(parsed.payload):
            cmd_len = parsed.payload[i]
            i += 1
            cmd = parsed.payload[i : i + cmd_len]
            assert len(cmd) == cmd_len
            i += cmd_len
            print(f"{Colors.ON_WHITE}Multicommand: {cmd}{Colors.ENDC}")

            self._parse_message(cmd, direction)

    def _parse_message(self, message, direction):
        parsed_payload = self.panel.parse_message(message, direction)
        if parsed_payload is not None:
            print(f"{Colors.ON_WHITE}{parsed_payload}{Colors.ENDC}")
        else:
            print(
                f"{Colors.RED}No parser for {direction} message payload: {binascii.hexlify(message)}{Colors.ENDC}"
            )
        return parsed_payload

    def _parse_generic_mgsp_multiread(self, parsed, direction):
        print(f"{Colors.RED}No parser for {direction} mgsp_multiread{Colors.ENDC}")


def old_yaml_format_traverser(data):
    re_key = re.compile(r"peer(\d+)_(\d+)")
    for key, value in data.items():
        # example peer0_0, where 0 is peer number and 0 is index number
        matches = re_key.match(key)

        yield {
            "peer": int(matches.group(1)),
            "data": value,
            "index": int(matches.group(2)),
        }


def decrypt_file(file, password, max_packets: int = None):
    try:
        data = ordered_load(file, yaml.loader.SafeLoader)
        parser = PayloadParser()

        if "peers" in data and "packets" in data:
            iterator = data["packets"]
        else:
            iterator = old_yaml_format_traverser(data)

        n = 0
        for packet in iterator:
            value = packet["data"]
            key = packet["index"]
            if not value[0] == 0xAA:
                print(f"{Colors.RED}Not an IP packet: {value}{Colors.ENDC}")
                continue
            header = value[0:16]
            payload = value[16:]

            is_request = header[3] in [3, 4]
            print(
                f"{Colors.BLUE}PC->IP: " if is_request else f"{Colors.GREEN}IP->PC:\n",
                f"\theader: {binascii.hexlify(header)}\n",
                f"\tencrypted_payload: {binascii.hexlify(payload)}",
            )

            if is_request:
                parsed = IPMessageRequest.parse(value, password=password)
            else:
                parsed = IPMessageResponse.parse(value, password=password)

            if (
                parsed.header.command == IPMessageCommand.connect
                and parsed.header.message_type == IPMessageType.ip_request
            ):
                if parsed.header.sub_command == 0:
                    assert password == parsed.payload, "Wrong decryption password"

            if (
                parsed.header.command == IPMessageCommand.connect
                and parsed.header.message_type == IPMessageType.ip_response
            ):
                if parsed.header.sub_command == 0:
                    password = parsed.payload[1:17]
                    assert len(password) == 16, "Wrong password length"
                    print(f"{Colors.RED}Session password: {password}{Colors.ENDC}")
                elif parsed.header.sub_command == 3:
                    connection_result = parsed.payload[0] & 240
                    if connection_result == 16:
                        print(f"{Colors.RED}Successfully connected{Colors.ENDC}")
                    elif connection_result == 112:
                        print(f"{Colors.RED}Connection failed{Colors.ENDC}")
                    else:
                        print(f"{Colors.RED}Connected to unknown{Colors.ENDC}")

            print(
                f"\tpayload: {binascii.hexlify(parsed.payload)}\n",
                f"\tpayload_raw: {parsed.payload}",
            )

            print(parsed)
            print(Colors.ENDC)
            parser.parse(parsed)

            if not is_request:
                print(
                    "----end %s-------------------------------------------------------------"
                    % key
                )
            n += 1

            if max_packets is not None and n > max_packets:
                print(f"Force stopped on {max_packets} packets")
                return

    except yaml.YAMLError as exc:
        print(f"{Colors.RED}{exc}{Colors.ENDC}")


def decrypt_serial_file(file, pc_password=None, max_packets: int = None):
    import re

    line_re = re.compile(r"^(TX|RX) \[(\d+)\]: ([0-9A-Fa-f ]+)$")
    panel = create_panel(None)
    key_bytes = make_serial_key(pc_password) if pc_password else None
    n = 0
    for line in file:
        line = line.strip()
        if not line:
            continue
        m = line_re.match(line)
        if not m:
            print(f"{Colors.RED}Unrecognised line: {line}{Colors.ENDC}")
            continue
        direction, length, hex_data = m.group(1), int(m.group(2)), m.group(3)
        message = bytes.fromhex(hex_data.replace(" ", ""))
        if len(message) != length:
            print(
                f"{Colors.RED}Length mismatch: declared {length}, got {len(message)}{Colors.ENDC}"
            )
            continue

        color = Colors.BLUE if direction == "TX" else Colors.GREEN
        print(
            f"{color}{direction} [{length}]: {binascii.hexlify(message).decode()}{Colors.ENDC}"
        )

        if len(message) >= 2 and message[0] >> 4 == 0xE and message[1] == 0xFE:
            # Try full-AES decryption first (ESP32-style frames)
            if key_bytes:
                plaintext = decrypt_serial_message(message, key_bytes)
                if plaintext:
                    print(
                        f"{Colors.ON_WHITE}  AES-256 decrypted ({len(message)}b → {len(plaintext)}b): "
                        f"{binascii.hexlify(plaintext).decode()}{Colors.ENDC}"
                    )
                    try:
                        inner = panel.parse_message(
                            plaintext,
                            "topanel" if direction == "TX" else "frompanel",
                        )
                        if inner:
                            print(f"{Colors.ON_WHITE}  Parsed: {inner}{Colors.ENDC}")
                            if inner.fields.value.po.command == 0:
                                panel = create_panel(None, inner)
                    except Exception:
                        pass
                    continue

            # Fallback: BabyWare compact E0 FE (algorithm unknown, display structure only)
            try:
                parsed = Encrypted.parse(message)
                print(
                    f"{Colors.ON_WHITE}  Encrypted frame (compact): request_nr={parsed.fields.value.request_nr}"
                    f" data({len(parsed.fields.value.data)}b)={binascii.hexlify(parsed.fields.value.data).decode()}{Colors.ENDC}"
                )
            except Exception:
                print(
                    f"{Colors.ON_WHITE}  E0 FE frame ({len(message)}b, no key provided or unknown format){Colors.ENDC}"
                )
        else:
            try:
                parsed = panel.parse_message(
                    message, "topanel" if direction == "TX" else "frompanel"
                )
                if parsed:
                    print(f"{Colors.ON_WHITE}  {parsed}{Colors.ENDC}")
                    if parsed.fields.value.po.command == 0:
                        panel = create_panel(None, parsed)
                else:
                    print(
                        f"{Colors.RED}  No parser for message: {binascii.hexlify(message).decode()}{Colors.ENDC}"
                    )
            except Exception:
                print(f"{Colors.RED}  Parse error{Colors.ENDC}")
                traceback.print_exc()

        n += 1
        if max_packets is not None and n >= max_packets:
            print(f"Force stopped on {max_packets} packets")
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        type=argparse.FileType("r"),
        help="YAML file to parse. In wireshark right click on the first "
        "package, 'Follow->TCP Stream', 'Show and save data as': "
        "'YAML', copy contents to a file.",
    )
    parser.add_argument(
        "password",
        type=str,
        nargs="?",
        default="paradox",
        help="IP Module password for decryption (not required in --serial mode)",
    )
    parser.add_argument(
        "-n",
        "--packets",
        type=int,
        help="Packets to decrypt",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Parse a .serial capture file (TX/RX hex lines) instead of IP YAML",
    )
    parser.add_argument(
        "--pc-password",
        type=str,
        default=None,
        help="PC password for E0 FE AES-256 decryption attempt (serial mode only)",
    )

    args = parser.parse_args()

    if args.serial:
        decrypt_serial_file(args.file, args.pc_password, args.packets)
    else:
        decrypt_file(args.file, args.password.encode("utf8"), args.packets)


if __name__ == "__main__":
    main()
