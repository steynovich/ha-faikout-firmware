import json
from datetime import timedelta

from homeassistant.components.mqtt import async_publish
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.faikout.const import SIGNAL_DEVICE_UPDATE, STALE_AFTER, STALE_CHECK_INTERVAL
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


def test_device_is_outdated_only_when_version_differs_from_latest():
    device = FaikoutDevice(id="A", name="n", version="0old0000", target="T")
    assert device.is_outdated("1a347969") is True
    assert device.is_outdated("0old0000") is False


async def _publish(hass, payload=STATE):
    await async_publish(hass, "state/faikout_zolder", payload)
    await hass.async_block_till_done()


async def test_fresh_device_is_not_stale(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)

    assert tracker.is_stale("24587CDB4CC8") is False
    await tracker.async_stop()


async def test_device_silent_past_threshold_is_stale(hass, mqtt_mock, freezer):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)

    freezer.tick(STALE_AFTER - timedelta(seconds=1))
    assert tracker.is_stale("24587CDB4CC8") is False
    freezer.tick(timedelta(seconds=2))
    assert tracker.is_stale("24587CDB4CC8") is True
    await tracker.async_stop()


async def test_unchanged_message_refreshes_last_seen(hass, mqtt_mock, freezer):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)

    freezer.tick(STALE_AFTER - timedelta(minutes=1))
    await _publish(hass)  # identical payload: no signal, but the device is alive
    freezer.tick(timedelta(minutes=5))

    assert tracker.is_stale("24587CDB4CC8") is False
    await tracker.async_stop()


async def test_reappearing_device_is_fresh_again_and_signals(hass, mqtt_mock, freezer):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)
    freezer.tick(STALE_AFTER + timedelta(minutes=1))
    async_fire_time_changed(hass)  # the sweep announces the device as gone
    await hass.async_block_till_done()
    assert tracker.is_stale("24587CDB4CC8") is True

    calls: list[str] = []
    unsub = async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATE, calls.append)
    await _publish(hass)  # same payload as before going quiet

    assert tracker.is_stale("24587CDB4CC8") is False
    assert calls == ["24587CDB4CC8"]
    unsub()
    await tracker.async_stop()


async def test_unknown_device_is_stale(hass):
    assert FaikoutDeviceTracker(hass).is_stale("NOPE") is True


async def test_sweep_signals_a_device_once_when_it_goes_quiet(hass, mqtt_mock, freezer):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)

    calls: list[str] = []
    unsub = async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATE, calls.append)

    freezer.tick(STALE_AFTER + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == ["24587CDB4CC8"]

    freezer.tick(STALE_CHECK_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == ["24587CDB4CC8"]  # already announced
    unsub()
    await tracker.async_stop()


async def test_forget_drops_the_device(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    await _publish(hass)

    tracker.forget("24587CDB4CC8")

    assert tracker.devices == {}
    assert tracker.is_stale("24587CDB4CC8") is True
    tracker.forget("24587CDB4CC8")  # forgetting twice is harmless
    await tracker.async_stop()
