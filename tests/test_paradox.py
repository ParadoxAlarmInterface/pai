from unittest.mock import AsyncMock

import pytest

from paradox.hardware import Panel
from paradox.paradox import Paradox


@pytest.mark.asyncio
async def test_send_panic(mocker):
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.send_panic = AsyncMock()

    alarm.storage.get_container("partition").deep_merge(
        {1: {"id": 1, "key": "Partition 1"}}
    )
    alarm.storage.get_container("user").deep_merge({3: {"id": 3, "key": "User 3"}})

    assert await alarm.send_panic("1", "fire", "3")
    alarm.panel.send_panic.assert_called_once_with([1], "fire", 3)
    alarm.panel.send_panic.reset_mock()

    assert await alarm.send_panic("Partition 1", "fire", "User 3")
    alarm.panel.send_panic.assert_called_once_with([1], "fire", 3)


@pytest.mark.asyncio
async def test_control_doors(mocker):
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.control_doors = AsyncMock()

    alarm.storage.get_container("door").deep_merge({1: {"id": 1, "key": "Door 1"}})

    assert await alarm.control_door("1", "unlock")
    alarm.panel.control_doors.assert_called_once_with([1], "unlock")
    alarm.panel.control_doors.reset_mock()

    assert await alarm.control_door("Door 1", "unlock")
    alarm.panel.control_doors.assert_called_once_with([1], "unlock")


def _add_module_pgm(alarm, module_address, pgm_index):
    key = f"module{module_address}_pgm{pgm_index}"
    alarm.storage.get_container("module_pgm")[key] = {
        "id": pgm_index,
        "key": key,
        "label": f"Module {module_address} PGM {pgm_index}",
        "module_address": module_address,
        "pgm_index": pgm_index,
    }
    alarm.storage.update_container_object("module_pgm", key, {"on": False})
    return key


@pytest.mark.asyncio
async def test_control_output_regular_pgm_routes_to_control_outputs(mocker):
    """Regular PGM uses control_outputs, not control_module_pgm_outputs."""
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.control_outputs = AsyncMock(return_value=True)
    alarm.panel.control_module_pgm_outputs = AsyncMock(return_value=True)

    alarm.storage.get_container("pgm").deep_merge({1: {"id": 1, "key": "PGM 1"}})

    assert await alarm.control_output("PGM 1", "on")
    alarm.panel.control_outputs.assert_called_once()
    alarm.panel.control_module_pgm_outputs.assert_not_called()


@pytest.mark.asyncio
async def test_control_output_module_pgm_routes_to_control_module_pgm_outputs(mocker):
    """Module PGM uses control_module_pgm_outputs with the correct address and index."""
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.control_outputs = AsyncMock(return_value=True)
    alarm.panel.control_module_pgm_outputs = AsyncMock(return_value=True)

    _add_module_pgm(alarm, module_address=4, pgm_index=2)

    assert await alarm.control_output("module4_pgm2", "on_override")
    alarm.panel.control_module_pgm_outputs.assert_called_once_with(4, 2, "on_override")
    alarm.panel.control_outputs.assert_not_called()


@pytest.mark.asyncio
async def test_control_output_module_pgm_optimistic_state(mocker):
    """Accepted on_override sets on=True; off_override sets on=False."""
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.control_module_pgm_outputs = AsyncMock(return_value=True)

    key = _add_module_pgm(alarm, module_address=4, pgm_index=1)

    await alarm.control_output(key, "on_override")
    assert alarm.storage.get_container("module_pgm")[key]["on"] is True

    await alarm.control_output(key, "off_override")
    assert alarm.storage.get_container("module_pgm")[key]["on"] is False


@pytest.mark.asyncio
async def test_control_output_no_match_returns_false(mocker):
    """Returns False when the output key matches neither pgm nor module_pgm."""
    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)

    assert await alarm.control_output("nonexistent", "on") is False


# ── Framing mode propagation (issue #609) ───────────────────────────────────


def _start_communication_reply(product_id):
    """A real StartCommunicationResponse frame for the given product id."""
    from paradox.hardware.common import ProductIdEnum
    from paradox.hardware.parsers import StartCommunicationResponse

    payload = bytearray(37)
    payload[4] = int(ProductIdEnum.encmapping[product_id])
    payload[5] = 6  # firmware version
    payload[36] = sum(payload[:36]) % 256

    return StartCommunicationResponse.parse(bytes(payload))


def _initiate_communication_reply():
    from construct import Container

    return Container(
        fields=Container(
            value=Container(
                label=b"SP6000  ",
                application=Container(version=6, revision=91, build=0),
                serial_number=b"\x00\x01\x02\x03",
            )
        )
    )


@pytest.mark.asyncio
async def test_connect_pushes_panel_framing_mode_after_identification(mocker):
    """SP/Magellan panels use fixed length framing, EVO uses variable (issue #609).

    The framing mode is only known once StartCommunication identifies the
    panel, so it must be pushed to the connection after the panel object is
    recreated - not just from the generic pre-identification panel.
    """
    from paradox.hardware.spectra_magellan.panel import Panel as SpectraPanel

    alarm = Paradox()

    connection = mocker.MagicMock()
    connection.connect = AsyncMock(return_value=True)
    connection.close = AsyncMock()
    alarm._connection = connection

    mocker.patch.object(
        Paradox,
        "send_wait",
        AsyncMock(
            side_effect=[
                _initiate_communication_reply(),
                _start_communication_reply("SPECTRA_SP6000"),
            ]
        ),
    )
    mocker.patch.object(
        SpectraPanel, "initialize_communication", AsyncMock(return_value=True)
    )

    assert await alarm.connect()

    assert isinstance(alarm.panel, SpectraPanel)
    assert connection.variable_message_length.call_args_list[-1][0][0] is False


@pytest.mark.asyncio
async def test_connect_pushes_variable_framing_for_evo(mocker):
    """EVO keeps variable length framing, and it is re-pushed after detection."""
    from paradox.hardware.evo import Panel_EVO192

    alarm = Paradox()

    connection = mocker.MagicMock()
    connection.connect = AsyncMock(return_value=True)
    connection.close = AsyncMock()
    alarm._connection = connection

    mocker.patch.object(
        Paradox,
        "send_wait",
        AsyncMock(
            side_effect=[
                _initiate_communication_reply(),
                _start_communication_reply("DIGIPLEX_EVO_192"),
            ]
        ),
    )
    mocker.patch.object(
        Panel_EVO192, "initialize_communication", AsyncMock(return_value=True)
    )

    assert await alarm.connect()

    assert isinstance(alarm.panel, Panel_EVO192)
    assert connection.variable_message_length.call_count == 2
    assert connection.variable_message_length.call_args_list[-1][0][0] is True
