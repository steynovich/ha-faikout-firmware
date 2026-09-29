"""Tests for the firmware-update binary sensor platform."""

import json
from datetime import timedelta
from unittest.mock import patch

from homeassistant.components.mqtt import async_publish
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN, STALE_AFTER
from custom_components.faikout.device_tracker import FaikoutDevice, FaikoutDeviceTracker

STATE_OLD = json.dumps(
    {
        "id": "24587CDB4CC8",
        "app": "Faikout",
        "version": "0old0000",
        "build-suffix": "-S3-MINI-N4-R2",
    }
)
STATE_CURRENT = json.dumps(
    {
        "id": "24587CDB4CC8",
        "app": "Faikout",
        "version": "1a347969",
        "build-suffix": "-S3-MINI-N4-R2",
    }
)
STATE_UNKNOWN_TARGET = json.dumps(
    {
        "id": "AABBCCDDEEFF",
        "app": "Faikout",
        "version": "1a347969",
        "build-suffix": "-UNKNOWN-MODEL",
    }
)


async def _setup(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_update_available_when_versions_differ(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state is not None
    assert state.state == "on"
    # Name resolves from the entity translation, not a hardcoded _attr_name.
    assert state.attributes["friendly_name"] == "faikout_zolder Firmware update"
    assert state.attributes["installed_version"] == "0old0000"
    assert state.attributes["latest_version"] == "1a347969"
    # The channel is reported from the coordinator, the one object that resolved it.
    assert state.attributes["channel"] == "beta"
    assert state.attributes["target"] == "Faikout-S3-MINI-N4-R2"


async def test_up_to_date_when_versions_match(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_CURRENT)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state.state == "off"


async def test_second_state_update_refreshes_existing_entity(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()
    await async_publish(hass, "state/faikout_zolder", STATE_CURRENT)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state.state == "off"
    assert state.attributes["installed_version"] == "1a347969"


async def test_unavailable_when_target_has_no_latest_version(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_unknown", STATE_UNKNOWN_TARGET)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_unknown_firmware_update")
    assert state is not None
    assert state.state == "unavailable"


async def test_preexisting_device_gets_entity_at_setup(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)
    device = FaikoutDevice(
        id="112233445566",
        name="faikout_preexisting",
        version="1a347969",
        target="Faikout-S3-MINI-N4-R2",
    )
    original_start = FaikoutDeviceTracker.async_start

    async def _fake_start(self):
        await original_start(self)
        self.track(device)

    with (
        patch(
            "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
            return_value="1a347969",
        ),
        patch.object(FaikoutDeviceTracker, "async_start", _fake_start),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_preexisting_firmware_update")
    assert state is not None
    assert state.state == "off"

    # A dispatcher signal for a *different* device must not touch this entity.
    await async_publish(hass, "state/faikout_zolder", STATE_CURRENT)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.faikout_preexisting_firmware_update")
    assert state.state == "off"


async def test_unavailable_when_device_goes_quiet_and_recovers(hass, mqtt_mock, freezer):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()
    entity_id = "binary_sensor.faikout_zolder_firmware_update"
    assert hass.states.get(entity_id).state == "on"

    freezer.tick(STALE_AFTER + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"

    # Same payload as before it went quiet: the device is back, nothing else changed.
    await async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"


async def test_sensor_survives_its_device_being_forgotten(hass, mqtt_mock):
    entry = await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()

    # Removal forgets the device before Home Assistant drops the entity; a state
    # write in that gap must not raise.
    entry.runtime_data.tracker.forget("24587CDB4CC8")
    entry.runtime_data.coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state.state == "unavailable"
