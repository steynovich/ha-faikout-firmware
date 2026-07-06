"""Tests for config entry diagnostics."""

import json
from unittest.mock import patch

from homeassistant.components.mqtt import async_publish
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN
from custom_components.faikout.diagnostics import async_get_config_entry_diagnostics

STATE = json.dumps(
    {
        "id": "24587CDB4CC8",
        "app": "Faikout",
        "version": "0old0000",
        "build-suffix": "-S3-MINI-N4-R2",
    }
)


async def test_diagnostics_reports_channel_versions_and_redacts_id(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await async_publish(hass, "state/faikout_zolder", STATE)
        await hass.async_block_till_done()

        result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["channel"] == "beta"
    assert result["latest_versions"] == {"Faikout-S3-MINI-N4-R2": "1a347969"}
    assert len(result["devices"]) == 1
    device = result["devices"][0]
    assert device["id"] == "**REDACTED**"
    assert device["name"] == "faikout_zolder"
    assert device["version"] == "0old0000"
    assert device["target"] == "Faikout-S3-MINI-N4-R2"
