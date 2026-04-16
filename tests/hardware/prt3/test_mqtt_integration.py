"""
MQTT / HA-discovery integration tests for PRT3.

Coverage:
  - panel_detected emitted from connect() with synthetic DetectedPanel
  - UtilityKeyButton.serialize() produces correct HA discovery JSON
  - MQTTAutodiscoveryEntityFactory.make_utility_key_button wires correctly
  - HomeAssistantMQTTInterface._publish_utility_key_configs publishes one
    config per key in PRT3_UTILITY_KEYS
  - PRT3Event.from_prt3 sets timestamp and subtype for event passthrough
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from paradox.data.model import DetectedPanel
from paradox.interfaces.mqtt.entities.button import UtilityKeyButton
from paradox.interfaces.mqtt.entities.device import Device
from paradox.interfaces.mqtt.entities.factory import MQTTAutodiscoveryEntityFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(serial="prt3_ttyusb0", model="PRT3"):
    panel = DetectedPanel(
        product_id=None,
        model=model,
        firmware_version="N/A",
        serial_number=serial,
    )
    return Device(panel)


# ---------------------------------------------------------------------------
# panel_detected emission on PRT3 connect()
# ---------------------------------------------------------------------------


async def test_prt3_connect_emits_panel_detected(monkeypatch):
    """After COMM&ok, connect() must publish panel_detected with model='PRT3'."""
    import paradox.paradox as paradox_module
    from paradox.paradox import Paradox
    from paradox.data.enums import RunState

    monkeypatch.setattr(paradox_module.cfg, "CONNECTION_TYPE", "PRT3")
    monkeypatch.setattr(paradox_module.cfg, "PRT3_SERIAL_PORT", "/dev/ttyUSB0")

    paradox = Paradox.__new__(Paradox)
    paradox.request_lock = asyncio.Lock()
    paradox.busy = asyncio.Lock()
    paradox.loop_wait_event = asyncio.Event()
    paradox._run_state = RunState.STOP
    paradox.work_loop = None
    paradox.panel = None
    paradox._connection = None

    from paradox.data.memory_storage import MemoryStorage
    paradox.storage = MemoryStorage()

    # Mock connection.connect() → True
    mock_conn = AsyncMock()
    mock_conn.connect = AsyncMock(return_value=True)
    mock_conn.connected = True
    paradox._connection = mock_conn

    # Capture ps.sendMessage calls
    detected_panels = []

    original_send = paradox_module.ps.sendMessage

    def capture_send(topic, **kwargs):
        if topic == "panel_detected":
            detected_panels.append(kwargs.get("panel"))
        return original_send(topic, **kwargs)

    monkeypatch.setattr(paradox_module.ps, "sendMessage", capture_send)

    # Mock PRT3Panel.initialize_communication → True
    with patch("paradox.hardware.prt3.panel.PRT3Panel.initialize_communication",
               new=AsyncMock(return_value=True)):
        result = await paradox.connect()

    assert result is True
    assert len(detected_panels) == 1
    panel = detected_panels[0]
    assert isinstance(panel, DetectedPanel)
    assert panel.model == "PRT3"
    assert panel.serial_number.startswith("prt3_")
    # serial_number must be MQTT-topic-safe (no slashes)
    assert "/" not in panel.serial_number


async def test_prt3_connect_no_panel_detected_on_comm_fail(monkeypatch):
    """If COMM&fail is received, panel_detected must NOT be sent."""
    import paradox.paradox as paradox_module
    from paradox.paradox import Paradox
    from paradox.data.enums import RunState

    monkeypatch.setattr(paradox_module.cfg, "CONNECTION_TYPE", "PRT3")
    monkeypatch.setattr(paradox_module.cfg, "PRT3_SERIAL_PORT", "/dev/ttyUSB0")

    paradox = Paradox.__new__(Paradox)
    paradox.request_lock = asyncio.Lock()
    paradox.busy = asyncio.Lock()
    paradox.loop_wait_event = asyncio.Event()
    paradox._run_state = RunState.STOP
    paradox.work_loop = None
    paradox.panel = None
    paradox._connection = None

    from paradox.data.memory_storage import MemoryStorage
    paradox.storage = MemoryStorage()

    mock_conn = AsyncMock()
    mock_conn.connect = AsyncMock(return_value=True)
    paradox._connection = mock_conn

    detected_panels = []
    original_send = paradox_module.ps.sendMessage

    def capture_send(topic, **kwargs):
        if topic == "panel_detected":
            detected_panels.append(kwargs.get("panel"))
        return original_send(topic, **kwargs)

    monkeypatch.setattr(paradox_module.ps, "sendMessage", capture_send)

    with patch("paradox.hardware.prt3.panel.PRT3Panel.initialize_communication",
               new=AsyncMock(return_value=False)):
        result = await paradox.connect()

    assert result is False
    assert detected_panels == []


# ---------------------------------------------------------------------------
# UtilityKeyButton serialisation
# ---------------------------------------------------------------------------


def test_utility_key_button_command_topic(monkeypatch):
    """command_topic must use MQTT_BASE_TOPIC / MQTT_CONTROL_TOPIC / MQTT_UTILITY_KEY_TOPIC."""
    import paradox.interfaces.mqtt.entities.button as btn_module

    monkeypatch.setattr(btn_module.cfg, "MQTT_BASE_TOPIC", "paradox")
    monkeypatch.setattr(btn_module.cfg, "MQTT_CONTROL_TOPIC", "control")
    monkeypatch.setattr(btn_module.cfg, "MQTT_UTILITY_KEY_TOPIC", "utility_key")

    device = _make_device()
    button = UtilityKeyButton(5, "Lock Door", device, "paradox/status")

    assert button.command_topic == "paradox/control/utility_key/5"


def test_utility_key_button_configuration_topic(monkeypatch):
    """configuration_topic must use HA discovery prefix / 'button' / serial / entity_id / 'config'."""
    import paradox.interfaces.mqtt.entities.button as btn_module

    monkeypatch.setattr(btn_module.cfg, "MQTT_HOMEASSISTANT_DISCOVERY_PREFIX", "homeassistant")

    device = _make_device(serial="prt3_ttyusb0")
    button = UtilityKeyButton(5, "Lock Door", device, "paradox/status")

    assert button.configuration_topic == "homeassistant/button/prt3_ttyusb0/utility_key_5/config"


def test_utility_key_button_serialize_keys(monkeypatch):
    """serialize() must include payload_press and command_topic; must not include state_topic."""
    import paradox.interfaces.mqtt.entities.button as btn_module

    monkeypatch.setattr(btn_module.cfg, "MQTT_BASE_TOPIC", "paradox")
    monkeypatch.setattr(btn_module.cfg, "MQTT_CONTROL_TOPIC", "control")
    monkeypatch.setattr(btn_module.cfg, "MQTT_UTILITY_KEY_TOPIC", "utility_key")
    monkeypatch.setattr(btn_module.cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "")

    device = _make_device()
    button = UtilityKeyButton(5, "Lock Door", device, "paradox/status")
    config = button.serialize()

    assert config["payload_press"] == "trigger"
    assert "command_topic" in config
    assert "state_topic" not in config
    assert config["name"] == "Lock Door"
    assert "prt3_ttyusb0" in config["unique_id"]


def test_utility_key_button_label_fallback(monkeypatch):
    """Empty label falls back to 'Utility Key {n}'."""
    import paradox.interfaces.mqtt.entities.button as btn_module

    monkeypatch.setattr(btn_module.cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "")

    device = _make_device()
    button = UtilityKeyButton(7, "", device, "paradox/status")
    config = button.serialize()

    assert config["name"] == "Utility Key 7"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_make_utility_key_button(monkeypatch):
    import paradox.interfaces.mqtt.entities.button as btn_module

    monkeypatch.setattr(btn_module.cfg, "MQTT_BASE_TOPIC", "paradox")
    monkeypatch.setattr(btn_module.cfg, "MQTT_CONTROL_TOPIC", "control")
    monkeypatch.setattr(btn_module.cfg, "MQTT_UTILITY_KEY_TOPIC", "utility_key")
    monkeypatch.setattr(btn_module.cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "")

    device = _make_device()
    factory = MQTTAutodiscoveryEntityFactory("paradox/status", device)

    button = factory.make_utility_key_button(3, "Garden Lights")

    assert isinstance(button, UtilityKeyButton)
    assert button.key_num == 3
    assert button.label == "Garden Lights"
    assert button.command_topic == "paradox/control/utility_key/3"


# ---------------------------------------------------------------------------
# HomeAssistantMQTTInterface._publish_utility_key_configs
# ---------------------------------------------------------------------------


def test_publish_utility_key_configs_publishes_one_per_key(monkeypatch):
    """_publish_utility_key_configs must call _publish_config once per valid key."""
    import paradox.interfaces.mqtt.homeassistant as ha_module

    monkeypatch.setattr(ha_module.cfg, "MQTT_BASE_TOPIC", "paradox")
    monkeypatch.setattr(ha_module.cfg, "MQTT_CONTROL_TOPIC", "control")
    monkeypatch.setattr(ha_module.cfg, "MQTT_UTILITY_KEY_TOPIC", "utility_key")
    monkeypatch.setattr(ha_module.cfg, "MQTT_HOMEASSISTANT_DISCOVERY_PREFIX", "homeassistant")
    monkeypatch.setattr(ha_module.cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "")

    from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface

    iface = HomeAssistantMQTTInterface.__new__(HomeAssistantMQTTInterface)
    device = _make_device()
    iface.entity_factory = MQTTAutodiscoveryEntityFactory("paradox/status", device)
    iface._publish_config = MagicMock()

    iface._publish_utility_key_configs({1: "Lock Front", 5: "Garden Lights"})

    assert iface._publish_config.call_count == 2
    published = [c.args[0] for c in iface._publish_config.call_args_list]
    topics = {b.configuration_topic for b in published}
    assert "homeassistant/button/prt3_ttyusb0/utility_key_1/config" in topics
    assert "homeassistant/button/prt3_ttyusb0/utility_key_5/config" in topics


def test_publish_utility_key_configs_skips_invalid_keys(monkeypatch):
    """Non-integer keys in PRT3_UTILITY_KEYS are skipped with a warning."""
    import paradox.interfaces.mqtt.homeassistant as ha_module

    monkeypatch.setattr(ha_module.cfg, "MQTT_BASE_TOPIC", "paradox")
    monkeypatch.setattr(ha_module.cfg, "MQTT_CONTROL_TOPIC", "control")
    monkeypatch.setattr(ha_module.cfg, "MQTT_UTILITY_KEY_TOPIC", "utility_key")
    monkeypatch.setattr(ha_module.cfg, "MQTT_HOMEASSISTANT_ENTITY_PREFIX", "")

    from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface

    iface = HomeAssistantMQTTInterface.__new__(HomeAssistantMQTTInterface)
    device = _make_device()
    iface.entity_factory = MQTTAutodiscoveryEntityFactory("paradox/status", device)
    iface._publish_config = MagicMock()

    iface._publish_utility_key_configs({"bad": "Label", 2: "Valid"})

    assert iface._publish_config.call_count == 1


# ---------------------------------------------------------------------------
# PRT3Event timestamp and subtype for event passthrough
# ---------------------------------------------------------------------------


def test_prt3_event_has_current_timestamp():
    import time
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    before = int(time.time())
    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=10, number=1, area=1))
    after = int(time.time())

    assert before <= evt.timestamp <= after


def test_prt3_event_has_subtype():
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=10, number=1, area=1))
    assert evt.subtype == "arm"


def test_prt3_event_unknown_group_has_subtype_unknown():
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=999, number=0, area=0))
    assert evt.subtype == "unknown"


def test_prt3_event_props_includes_subtype_and_timestamp():
    """event.props must surface subtype and a non-zero timestamp for MQTT passthrough."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=1, number=3, area=1))
    props = evt.props

    assert "subtype" in props
    assert props["subtype"] == "open"
    assert "timestamp" in props
    assert props["timestamp"] > 0


# ---------------------------------------------------------------------------
# Exit-delay / arming-state events (G065 per-N dispatch)
# ---------------------------------------------------------------------------


def test_g065_n1_sets_exit_delay():
    """G065N001 must set exit_delay=True so paradox.py maps current_state='arming'."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=65, number=1, area=2))

    assert evt.change.get("exit_delay") is True
    assert "arm" not in evt.change, "G065N001 must not set arm=True (causes flicker)"
    assert evt.subtype == "exit_delay"
    assert evt.id == 2   # partition element_id == area


def test_g065_n2_sets_entry_delay():
    """G065N002 must set entry_delay=True."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    evt = PRT3Event.from_prt3(PRT3SystemEvent(group=65, number=2, area=1))

    assert evt.change.get("entry_delay") is True
    assert evt.subtype == "entry_delay"


def test_g065_other_n_is_noop():
    """G065 with N values other than 1/2 produce no state change (fallback no-op)."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    for n in (0, 3, 4, 5):
        evt = PRT3Event.from_prt3(PRT3SystemEvent(group=65, number=n, area=1))
        assert evt.change == {}, f"G065N{n:03d} should be a no-op, got {evt.change}"


def test_arm_event_clears_exit_delay():
    """G010 (arm by user) must set arm=True AND exit_delay=False."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    for group in (10, 11, 12, 13):
        evt = PRT3Event.from_prt3(PRT3SystemEvent(group=group, number=1, area=1))
        assert evt.change.get("arm") is True, f"G{group:03d} must set arm=True"
        assert evt.change.get("exit_delay") is False, \
            f"G{group:03d} must clear exit_delay to avoid stale arming state"


def test_disarm_event_clears_exit_delay():
    """G014-G017 and G020 (disarm) must clear exit_delay so a cancelled arm resets HA state."""
    from paradox.hardware.prt3.parser import PRT3SystemEvent
    from paradox.hardware.prt3.event import PRT3Event

    for group in (14, 15, 16, 17, 20):
        evt = PRT3Event.from_prt3(PRT3SystemEvent(group=group, number=1, area=1))
        assert evt.change.get("arm") is False, f"G{group:03d} must set arm=False"
        assert evt.change.get("exit_delay") is False, \
            f"G{group:03d} must clear exit_delay (cancels in-progress arming)"
