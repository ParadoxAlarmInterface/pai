from binascii import unhexlify
from paradox.hardware.evo.parsers import ErrorMessage


def test_panel_not_connected():
    raw = unhexlify('70041084')

    data = ErrorMessage.parse(raw)

    assert "panel_not_connected" == data.fields.value.message
    assert "panel_not_connected" == str(data.fields.value.message)
    assert 0x10 == int(data.fields.value.message)
    print(data)
