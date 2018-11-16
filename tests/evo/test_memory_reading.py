import binascii
from paradox.hardware.evo import ReadEEPROM, ReadEEPROMResponse

eeprom_request_bin = binascii.unhexlify('500800009f004037')
eeprom_response_bin = binascii.unhexlify(
    '524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e85')

ram_request_bin = binascii.unhexlify('5008800000104028')
ram_response_bin = binascii.unhexlify(
    '524780000010040200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002fd2')


def test_parse_read_eeprom():
    request = ReadEEPROM.parse(eeprom_request_bin)
    response = ReadEEPROMResponse.parse(eeprom_response_bin)

    print(request)
    print(response)

    assert request.fields.value.control.ram_access == False
    assert response.fields.value.control.ram_access == False
    assert request.fields.value.address == response.fields.value.address
    assert request.fields.value.length == len(response.fields.value.data)


def test_parse_read_ram():
    request = ReadEEPROM.parse(ram_request_bin)
    response = ReadEEPROMResponse.parse(ram_response_bin)

    print(request)
    print(response)

    assert request.fields.value.control.ram_access == True
    assert response.fields.value.control.ram_access == True
    assert request.fields.value.address == response.fields.value.address
    assert request.fields.value.length == len(response.fields.value.data)


def test_build_read_eeprom():
    assert ReadEEPROM.build(dict(fields=dict(value=dict(address=40704, length=64)))) == eeprom_request_bin


def test_build_read_ram():
    assert ReadEEPROM.build(
        dict(fields=dict(value=dict(address=16, length=64, control=dict(ram_access=True))))) == ram_request_bin
