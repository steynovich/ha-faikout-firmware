"""Tests for entry setup and unload wiring."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout import async_unload_entry
from custom_components.faikout.const import CONF_CHANNEL, DOMAIN, Channel
from custom_components.faikout.ota.exceptions import FirmwareFetchError


async def test_setup_and_unload(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.coordinator.data == {"Faikout-S3-MINI-N4-R2": "1a347969"}

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_stops_tracker_when_first_refresh_fails(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        side_effect=FirmwareFetchError("boom"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_options_update_reloads_with_new_channel(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "stable"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.coordinator.channel is Channel.STABLE

        hass.config_entries.async_update_entry(entry, options={CONF_CHANNEL: "beta"})
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.channel is Channel.BETA


async def test_unload_entry_skips_tracker_stop_when_platform_unload_fails(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    tracker = entry.runtime_data.tracker
    with (
        patch.object(hass.config_entries, "async_unload_platforms", return_value=False),
        patch.object(tracker, "async_stop") as mock_stop,
    ):
        assert await async_unload_entry(hass, entry) is False

    # The tracker is left running because the platforms did not unload.
    mock_stop.assert_not_called()
