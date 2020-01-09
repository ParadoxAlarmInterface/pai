import binascii

import pytest

from paradox.hardware.spectra_magellan.panel import Panel
from paradox.hardware.spectra_magellan.parsers import ReadEEPROMResponse

# Label loading
request_reply_map = {
    b'50000010000000000000000000000000000000000000000000000000000000000001000061': b'52000010456c04749672202020202020202020204e617070616c69202020202020202020b8',
    b'50000020000000000000000000000000000000000000000000000000000000000001000071': b'520000204e617070616c692020202020202020204b6f6e7968612020202020202020202001',
    b'50000030000000000000000000000000000000000000000000000000000000000001000081': b'520000304b6f6e796861202020202020202020204d616d6120737a6f6261202020202020a7',
    b'50000040000000000000000000000000000000000000000000000000000000000001000091': b'520000404d616d6120737a6f626120202020202047796572656b20737a6f62612020202033'
}


# 2019-12-04 13:09:38,232 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER
# 2019-12-04 13:09:38,323 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI
# 2019-12-04 13:09:38,332 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER
# 2019-12-04 13:09:38,418 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI
# 2019-12-04 13:09:38,426 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER
# 2019-12-04 13:09:38,514 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI
# 2019-12-04 13:09:38,522 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000500000000000000000000000000000000000000000000000000000000000010000a1'
# 2019-12-04 13:09:38,609 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'5200005047796572656b20737a6f6261202020205a6f7a8d20737a6f626120202020202097'
# 2019-12-04 13:09:38,617 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000600000000000000000000000000000000000000000000000000000000000010000b1'
# 2019-12-04 13:09:38,721 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000605a6f7a8d20737a6f62612020202020204c967063738e689d7a2020202020202096'
# 2019-12-04 13:09:38,729 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000700000000000000000000000000000000000000000000000000000000000010000c1'
# 2019-12-04 13:09:38,816 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000704c967063738e689d7a20202020202020537a61626f749d7a7320202020202020b4'
# 2019-12-04 13:09:38,825 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000800000000000000000000000000000000000000000000000000000000000010000d1'
# 2019-12-04 13:09:38,912 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'52000080537a61626f749d7a7320202020202020456c04749672206e7969749d7320202034'
# 2019-12-04 13:09:38,920 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000900000000000000000000000000000000000000000000000000000000000010000e1'
# 2019-12-04 13:09:39,007 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'52000090456c04749672206e7969749d732020204e617070616c69206e7969749d73202060'
# 2019-12-04 13:09:39,016 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000a00000000000000000000000000000000000000000000000000000000000010000f1'
# 2019-12-04 13:09:39,103 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000a04e617070616c69206e7969749d73202042656a9d72617469206e7969749d73205d'
# 2019-12-04 13:09:39,111 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000b0000000000000000000000000000000000000000000000000000000000001000001'
# 2019-12-04 13:09:39,199 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000b042656a9d72617469206e7969749d73204d616d61206e7969749d73202020202084'
# 2019-12-04 13:09:39,207 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000c0000000000000000000000000000000000000000000000000000000000001000011'
# 2019-12-04 13:09:39,310 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000c04d616d61206e7969749d73202020202047796572656b206e7969749d73202020dd'
# 2019-12-04 13:09:39,318 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000d0000000000000000000000000000000000000000000000000000000000001000021'
# 2019-12-04 13:09:39,406 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000d047796572656b206e7969749d73202020466f6c796f738d20202020202020202006'
# 2019-12-04 13:09:39,413 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000e0000000000000000000000000000000000000000000000000000000000001000031'
# 2019-12-04 13:09:39,501 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000e0466f6c796f738d2020202020202020205a6f6e652031352020202020202020209d'
# 2019-12-04 13:09:39,509 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'500000f0000000000000000000000000000000000000000000000000000000000001000041'
# 2019-12-04 13:09:39,597 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520000f05a6f6e652031352020202020202020205a6f6e65203136202020202020202020c7'
# 2019-12-04 13:09:39,605 - DEBUG    - PAI.paradox.connections.serial_connection - PAI -> SER b'50000100000000000000000000000000000000000000000000000000000000000001000052'
# 2019-12-04 13:09:39,693 - DEBUG    - PAI.paradox.connections.serial_connection - SER -> PAI b'520001005a6f6e652031362020202020202020205a6f6e65203137202020202020202020da'
# 2019-12-04 13:09:39,697 - INFO     - PAI.paradox.hardware.panel - Zone: Eltr, Nappali, Konyha, Mama szoba, Gyerek szoba, Zoz szoba, Lpcshz, Szabotzs, Eltr nyits, Nappali nyits, Bejrati nyits, Mama nyits, Gyerek nyits, Folyos, Zone 15, Zone 16


async def send_wait(message_type, args, reply_expected):
    out_raw = message_type.build(dict(fields=dict(value=args)))
    in_raw = binascii.unhexlify(request_reply_map[binascii.hexlify(out_raw)])

    return ReadEEPROMResponse.parse(in_raw)


@pytest.mark.asyncio
async def test_label_loading(mocker):
    config = mocker.patch("paradox.hardware.panel.cfg")
    config.LIMITS = {
        "zone": [1],
        "pgm": [],
        "partition": [],
        "user": [],
        "bus-module": [],
        "repeater": [],
        "keypad": [],
        "site": [],
        "siren": []
    }
    config.LABEL_ENCODING = 'latin2'

    core = mocker.MagicMock()
    core.send_wait = send_wait
    panel = Panel(core=core, product_id=0)

    print(await panel.load_labels())
