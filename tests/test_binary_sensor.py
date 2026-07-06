"""Tests for the firmware-update binary sensor platform."""

import json
from unittest.mock import patch

from homeassistant.components.mqtt import async_publish
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN

STATE_OLD = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "0old0000",
    "build-suffix": "-S3-MINI-N4-R2",
})
STATE_CURRENT = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
    "build-suffix": "-S3-MINI-N4-R2",
})


async def _setup(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
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
    assert state.attributes["installed_version"] == "0old0000"
    assert state.attributes["latest_version"] == "1a347969"


async def test_up_to_date_when_versions_match(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await async_publish(hass, "state/faikout_zolder", STATE_CURRENT)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state.state == "off"
