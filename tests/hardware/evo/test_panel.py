from paradox.hardware import create_panel
from paradox.hardware.evo import Panel_EVO192
from paradox.hardware.parsers import StartCommunicationResponse


def create_evo192_panel(alarm=None):
    payload = b"\x00\x00\x00\x00\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05"
    data = StartCommunicationResponse.parse(payload)

    return create_panel(alarm, data)


def test_create_panel():
    panel = create_evo192_panel()

    assert isinstance(panel, Panel_EVO192)
