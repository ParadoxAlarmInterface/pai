#!/usr/bin/env python3
import argparse
import binascii
from collections import OrderedDict

import yaml

from paradox.connections.ip.parsers import IPMessageRequest, IPMessageResponse
from paradox.hardware import create_panel


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
        message_type = parsed.header.message_type
        if message_type in [
            "serial_passthrough_request",
            "serial_passthrough_response",
        ]:
            if message_type == "serial_passthrough_request":
                parsed_payload = self.panel.parse_message(parsed.payload)
                if parsed_payload is not None:
                    print(parsed_payload)
                else:
                    print("No parser available for the message")
            else:
                parsed_payload = self.panel.parse_message(
                    parsed.payload, direction="frompanel"
                )
                if parsed_payload is not None:
                    if parsed_payload is not None:
                        print(parsed_payload)
                    else:
                        print("No parser available for the message")

                    if parsed_payload.fields.value.po.command == 0:  # panel detection
                        product_id = parsed_payload.fields.value.product_id
                        self.panel = create_panel(None, product_id)
                    if parsed_payload.fields.value.po.command == 5:  # eeprom/ram read
                        if (
                            parsed_payload.fields.value.control.ram_access
                            and parsed_payload.fields.value.control._eeprom_address_bits
                            == 0
                            and parsed_payload.fields.value.bus_address == 0
                        ):
                            ram_address = parsed_payload.fields.value.address
                            ram_parser = self.panel.get_message("RAMDataParserMap").get(
                                ram_address
                            )
                            if ram_parser is not None:
                                print(
                                    ram_parser.parse(parsed_payload.fields.value.data)
                                )
                            else:
                                print(
                                    f"No parser for {ram_address} ram address, data: {binascii.hexlify(parsed_payload.fields.value.data)}"
                                )


def decrypt_file(file, password):
    try:
        data = ordered_load(file, yaml.loader.SafeLoader)
        parser = PayloadParser()

        n = 0
        for key, value in data.items():
            header = value[0:16]

            if "peer0_" in key:
                parsed = IPMessageRequest.parse(value, password=password)
            else:
                parsed = IPMessageResponse.parse(value, password=password)

            if (
                parsed.header.command == "ip_authentication"
                and parsed.header.message_type == "ip_request"
            ):
                assert password == parsed.payload, "Wrong decryption password"

            if (
                parsed.header.command == "ip_authentication"
                and parsed.header.message_type == "ip_response"
            ):
                password = parsed.payload[1:17]

            print(
                "PC->IP: " if "peer0_" in key else "IP->PC: ",
                f"header: {binascii.hexlify(header)}",
                f"body: {binascii.hexlify(parsed.payload)}",
                f"body_raw: {parsed.payload}",
            )

            print(parsed)
            parser.parse(parsed)

            if "peer1_" in key:
                print(
                    "----end %s-------------------------------------------------------------"
                    % key
                )
            n += 1

    except yaml.YAMLError as exc:
        print(exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        type=argparse.FileType("r"),
        help="YAML file to parse. In wireshark right click on the first "
        "package, 'Follow->TCP Stream', 'Show and save data as': "
        "'YAML', copy contents to a file.",
    )
    parser.add_argument("password", type=str, help="IP Module password for decryption")

    args = parser.parse_args()

    decrypt_file(args.file, args.password.encode("utf8"))


if __name__ == "__main__":
    main()
