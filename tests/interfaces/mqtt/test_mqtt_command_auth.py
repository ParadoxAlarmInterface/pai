import asyncio
import datetime
import hashlib
import json

import pytest
from paho.mqtt.client import MQTTMessage

from paradox.config import config as cfg
from paradox.event import Event
from paradox.interfaces.mqtt.basic import BasicMQTTInterface


async def async_magic():
    pass


SECRET = "secret1234"
SECRET_USER = "UserA"


def get_interface(mocker, secret):
    cfg.MQTT_CHALLENGE_SECRET = secret
    cfg.MQTT_ENABLE = True
    mocker.MagicMock.__await__ = (
        lambda x: async_magic().__await__()
    )  # Deal with await error

    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_event_loop())
    con = mocker.patch("paradox.interfaces.mqtt.core.MQTTConnection")
    con.get_instance.return_value.connected = True
    interface = BasicMQTTInterface(mocker.MagicMock())
    interface.start()
    interface.on_connect(None, None, None, None)

    return interface


def calc_response(challenge, secret, rounds):
    h = hashlib.new("SHA1")
    i = rounds
    text = f"{challenge}{secret}".encode("utf-8")

    while i > 0:
        h.update(text)
        i -= 1

    return h.hexdigest()


@pytest.mark.asyncio
async def test_validate_challenge(mocker):
    interface = get_interface(mocker, SECRET)
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        res = interface._validate_command_with_challenge("arm XXXX")
        assert res[0] is None
        assert res[1] is None

        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)

        res = interface._validate_command_with_challenge(f"arm {resp}")
        assert res[0] == 'arm'
        assert res[1] == None

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_validate_challenge_user(mocker):
    interface = get_interface(mocker, {SECRET_USER: SECRET})
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        res = interface._validate_command_with_challenge(f"arm {SECRET_USER} XXXX")
        assert res[0] is None
        assert res[1] == None

        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)

        res = interface._validate_command_with_challenge(f"arm {SECRET_USER} {resp}")
        assert res[0] == 'arm'
        assert res[1] == SECRET_USER

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_auth_output_control(mocker):
    interface = get_interface(mocker, SECRET)
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/outputs/Output01")
        message.payload = b"on XXX"

        # Auth fail due to invalid response
        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )

        interface.alarm.control_output.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"on {resp}".encode("utf-8")

        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication success. user: None",
            2,
            True,
        )

        interface.alarm.control_output.assert_called_once_with("Output01", "on")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/outputs/Output02")
        message.payload = f"on {resp}".encode("utf-8")

        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_output.assert_called_with("Output02", "on")
            assert False
        except AssertionError:
            pass

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_auth_output_control_user(mocker):
    interface = get_interface(mocker, {SECRET_USER: SECRET})
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/outputs/Output01")
        message.payload = f"on {SECRET_USER} XXX".encode('utf-8')

        # Auth fail due to invalid response
        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )

        interface.alarm.control_output.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"on {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication success. user: {SECRET_USER}",
            2,
            True,
        )
        interface.alarm.control_output.assert_called_once_with("Output01", "on")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/outputs/Output02")
        message.payload = f"on {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_output_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_output.assert_called_with("Output02", "on")
            assert False
        except AssertionError:
            pass
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_auth_partition_control(mocker):
    interface = get_interface(mocker, SECRET)
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/partitions/Partition01")
        message.payload = b"arm XXX"

        # Auth fail due to invalid response
        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )
        interface.alarm.control_partition.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"arm {resp}".encode("utf-8")

        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication success. user: None",
            2,
            True,
        )

        interface.alarm.control_partition.assert_called_once_with("Partition01", "arm")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/partitions/Partition02")
        message.payload = f"arm {resp}".encode("utf-8")

        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_partition.assert_called_with("Partition02", "arm")
            assert False
        except AssertionError:
            pass

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_auth_partition_control_user(mocker):
    interface = get_interface(mocker, {SECRET_USER: SECRET})
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/partitions/Partition01")
        message.payload = f"arm {SECRET_USER} XXX".encode('utf-8')

        # Auth fail due to invalid response
        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )
        interface.alarm.control_partition.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"arm {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.alarm.control_partition.assert_called_once_with("Partition01", "arm")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication success. user: {SECRET_USER}",
            2,
            True,
        )
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/partitions/Partition02")
        message.payload = f"arm {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_partition_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_partition.assert_called_with("Partition02", "arm")
            assert False
        except AssertionError:
            pass

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()


@pytest.mark.asyncio
async def test_auth_zone_control(mocker):
    interface = get_interface(mocker, SECRET)
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/zones/zone01")
        message.payload = b"bypass XXX"

        # Auth fail due to invalid response
        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )
        interface.alarm.control_zone.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"bypass {resp}".encode("utf-8")

        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication success. user: None",
            2,
            True,
        )
        interface.alarm.control_zone.assert_called_once_with("zone01", "bypass")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/zones/zone02")
        message.payload = f"bypass {resp}".encode("utf-8")

        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_zone.assert_called_with("zone02", "bypass")
            assert False
        except AssertionError:
            pass

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            "Authentication failed. user: None",
            2,
            True,
        )
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()

@pytest.mark.asyncio
async def test_auth_zone_control_user(mocker):
    interface = get_interface(mocker, {SECRET_USER: SECRET})
    try:
        await asyncio.sleep(0.01)
        interface._on_ready()
        await asyncio.sleep(0.01)

        # Basic init and first challenge
        interface.mqtt.publish.assert_called_once_with(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        message = MQTTMessage(topic=b"paradox/control/zones/zone01")
        message.payload = f"bypass {SECRET_USER} XXX".encode('utf-8')

        # Auth fail due to invalid response
        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )
        interface.alarm.control_zone.assert_not_called()
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )


        # Auth success
        interface.mqtt.publish.reset_mock()
        resp = calc_response(interface.challenge, SECRET, cfg.MQTT_CHALLENGE_ROUNDS)
        message.payload = f"bypass {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication success. user: {SECRET_USER}",
            2,
            True,
        )
        interface.alarm.control_zone.assert_called_once_with("zone01", "bypass")
        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

        # Auth fail due to challenge reuse (and bad response)
        interface.mqtt.publish.reset_mock()
        message = MQTTMessage(topic=b"paradox/control/zones/zone02")
        message.payload = f"bypass {SECRET_USER} {resp}".encode("utf-8")

        interface._mqtt_handle_zone_control(None, None, message)
        await asyncio.sleep(0.01)
        try:
            interface.alarm.control_zone.assert_called_with("zone02", "bypass")
            assert False
        except AssertionError:
            pass

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_STATUS_TOPIC}",
            f"Authentication failed. user: {SECRET_USER}",
            2,
            True,
        )

        interface.mqtt.publish.assert_any_call(
            f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_STATES_TOPIC}/{cfg.MQTT_CHALLENGE_TOPIC}",
            interface.challenge,
            2,
            True,
        )

    finally:
        interface.stop()
        interface.join()
        assert not interface.is_alive()