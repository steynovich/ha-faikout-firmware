import json

from homeassistant.components.mqtt import async_publish
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.faikout.const import SIGNAL_DEVICE_UPDATE
from custom_components.faikout.device_tracker import (
    FaikoutDevice,
    FaikoutDeviceTracker,
    parse_state_payload,
)

STATE = json.dumps(
    {
        "id": "24587CDB4CC8",
        "app": "Faikout",
        "version": "1a347969",
        "build-suffix": "-S3-MINI-N4-R2",
        "temp": 25.08,
    }
)


def test_parse_state_payload_ok():
    dev = parse_state_payload("state/faikout_zolder", STATE)
    assert dev == FaikoutDevice(
        id="24587CDB4CC8",
        name="faikout_zolder",
        version="1a347969",
        target="Faikout-S3-MINI-N4-R2",
    )


def test_parse_ignores_non_faikout():
    assert parse_state_payload("state/other", json.dumps({"app": "Other"})) is None


def test_parse_ignores_bad_json():
    assert parse_state_payload("state/x", "not json{") is None


def test_parse_ignores_missing_fields():
    assert parse_state_payload("state/x", json.dumps({"app": "Faikout"})) is None


async def test_tracker_records_device(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()

    await async_publish(hass, "state/faikout_zolder", STATE)
    await hass.async_block_till_done()
    assert tracker.devices["24587CDB4CC8"].version == "1a347969"
    await tracker.async_stop()


async def test_tracker_ignores_unparseable_message(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()

    await async_publish(hass, "state/other", json.dumps({"app": "Other"}))
    await hass.async_block_till_done()
    assert tracker.devices == {}
    await tracker.async_stop()


async def test_tracker_sends_signal_once_for_duplicate_state(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()

    calls: list[str] = []
    unsub = async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATE, calls.append)

    await async_publish(hass, "state/faikout_zolder", STATE)
    await hass.async_block_till_done()
    await async_publish(hass, "state/faikout_zolder", STATE)
    await hass.async_block_till_done()

    assert calls == ["24587CDB4CC8"]
    unsub()
    await tracker.async_stop()


def test_handle_message_ignores_non_str_payload(hass):
    tracker = FaikoutDeviceTracker(hass)
    msg = ReceiveMessage("state/faikout_zolder", b"\x00\x01", 0, False, "state/+", 0.0)
    tracker._handle_message(msg)
    assert tracker.devices == {}


async def test_async_stop_without_start_is_a_noop(hass):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_stop()
    await tracker.async_stop()
    assert tracker.devices == {}
