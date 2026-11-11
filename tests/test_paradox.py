from datetime import datetime
import json
from unittest.mock import AsyncMock

import pytest

from paradox.connections.connection import Connection
from paradox.config import Config, config as cfg
from paradox.hardware import Panel, create_panel
from paradox.paradox import Paradox


@pytest.mark.parametrize(
    "connection_type, product_id, supported",
    [
        ("Serial", "MAGELLAN_MG6250", False),
        ("PRT3", None, False),
        ("Serial", "DIGIPLEX_EVO_192", True),
        ("Serial", "MAGELLAN_MG5050", True),
    ],
)
async def test_sync_time_respects_panel_support(
    monkeypatch, mocker, connection_type, product_id, supported
):
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", connection_type)
    monkeypatch.setattr(cfg, "SYNC_TIME", True)
    monkeypatch.setattr(cfg, "SYNC_TIME_TIMEZONE", "")
    alarm = Paradox()
    alarm.panel = create_panel(
        alarm, _start_communication_reply(product_id) if product_id else None
    )
    alarm.storage.get_container("system").deep_merge(
        {"date": {"time": datetime(2000, 1, 1)}}
    )
    drift_check = mocker.spy(alarm, "_is_time_sync_required")
    alarm.send_wait = AsyncMock()

    await alarm.sync_time()

    if supported:
        drift_check.assert_called_once()
        alarm.send_wait.assert_awaited_once()
        assert alarm.send_wait.call_args.args[0] is alarm.panel.get_message(
            "SetTimeDate"
        )
    else:
        drift_check.assert_not_called()
        alarm.send_wait.assert_not_awaited()


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


def test_init_module_pgms_from_json(tmp_path, monkeypatch, mocker):
    options = tmp_path / "options.json"
    options.write_text(
        json.dumps(
            {
                "MODULE_PGM_ADDRESSES": [
                    {"address": 4, "pgm_count": 3},
                    {"address": 7, "pgm_count": 1},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("PAI_MODULE_PGM_ADDRESSES", raising=False)
    config = Config()
    config.load(str(options))
    mocker.patch("paradox.paradox.cfg", config)
    mocker.patch("paradox.lib.ps.sendChange")

    alarm = Paradox()
    alarm._init_module_pgms()
    outputs = alarm.storage.get_container("module_pgm")

    assert set(outputs) == {
        "module4_pgm1",
        "module4_pgm2",
        "module4_pgm3",
        "module7_pgm1",
    }
    assert outputs["module4_pgm3"]["module_address"] == 4
    assert outputs["module4_pgm3"]["pgm_index"] == 3
    assert outputs["module4_pgm3"]["on"] is False


def test_init_module_pgms_skips_invalid_and_duplicate_entries(
    monkeypatch, mocker, caplog
):
    monkeypatch.setattr(
        cfg,
        "MODULE_PGM_ADDRESSES",
        [
            "invalid",
            {"address": "4", "pgm_count": 3},
            {"address": True, "pgm_count": 1},
            {"address": 255, "pgm_count": 1},
            {"address": 4, "pgm_count": True},
            {"address": 4, "pgm_count": 5},
            {"address": 4, "pgm_count": 2},
            {"address": 4, "pgm_count": 4},
            {"address": 254, "pgm_count": 1},
        ],
    )
    mocker.patch("paradox.lib.ps.sendChange")

    alarm = Paradox()
    alarm._init_module_pgms()

    assert set(alarm.storage.get_container("module_pgm")) == {
        "module4_pgm1",
        "module4_pgm2",
        "module254_pgm1",
    }
    assert "invalid module entry" in caplog.text
    assert "invalid module address" in caplog.text
    assert "invalid pgm_count" in caplog.text
    assert "duplicate module address 4" in caplog.text


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

    connection = mocker.MagicMock(spec=Connection)
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

    connection = mocker.MagicMock(spec=Connection)
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
