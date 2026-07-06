import json

from custom_components.faikout.device_tracker import (
    FaikoutDevice, FaikoutDeviceTracker, parse_state_payload,
)

STATE = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
    "build-suffix": "-S3-MINI-N4-R2", "temp": 25.08,
})


def test_parse_state_payload_ok():
    dev = parse_state_payload("state/faikout_zolder", STATE)
    assert dev == FaikoutDevice(
        id="24587CDB4CC8", name="faikout_zolder",
        version="1a347969", target="Faikout-S3-MINI-N4-R2",
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
    from homeassistant.components.mqtt import async_publish
    await async_publish(hass, "state/faikout_zolder", STATE)
    await hass.async_block_till_done()
    assert tracker.devices["24587CDB4CC8"].version == "1a347969"
    await tracker.async_stop()
