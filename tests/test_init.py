"""Tests for entry setup and unload wiring."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout import (
    async_remove_config_entry_device,
    async_unload_entry,
)
from custom_components.faikout.const import CONF_CHANNEL, DOMAIN, Channel
from custom_components.faikout.ota.exceptions import FirmwareFetchError


async def test_setup_and_unload(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
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
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        side_effect=FirmwareFetchError("boom"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_options_update_reloads_with_new_channel(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "stable"})
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
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
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


async def test_v1_entry_migrates_channel_from_data_to_options(hass, mqtt_mock):
    # v0.1.0 stored the channel in entry.data; the options flow wrote it to
    # entry.options, leaving two sources of truth. Migration collapses them.
    entry = MockConfigEntry(domain=DOMAIN, version=1, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.options == {CONF_CHANNEL: "beta"}
    assert CONF_CHANNEL not in entry.data
    assert entry.runtime_data.coordinator.channel is Channel.BETA


async def test_v1_entry_migration_prefers_the_options_value(hass, mqtt_mock):
    # A v1 entry whose channel was already changed via the options flow must keep
    # the options value; entry.data still holds the stale original.
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={CONF_CHANNEL: "stable"},
        options={CONF_CHANNEL: "beta"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.options == {CONF_CHANNEL: "beta"}
    assert entry.runtime_data.coordinator.channel is Channel.BETA


async def test_entry_from_a_newer_version_is_refused(hass, mqtt_mock):
    # An entry written by a future release may hold data this code cannot read;
    # refuse the migration rather than setting up against a guessed shape.
    entry = MockConfigEntry(domain=DOMAIN, version=3, options={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_setup_survives_an_entry_with_no_channel(hass, mqtt_mock):
    # Defensive: a v2 entry with empty options must fall back to the default
    # channel rather than raising KeyError out of async_setup_entry.
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.channel is Channel.STABLE


async def test_stale_device_can_be_removed_manually(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "24587CDB4CC8")},
    )

    # Devices are only known from live MQTT, so manual removal is always allowed.
    assert await async_remove_config_entry_device(hass, entry, device) is True
