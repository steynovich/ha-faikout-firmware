"""The Faikout Firmware Update integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CHANNEL, Channel
from .coordinator import FaikoutCoordinator
from .device_tracker import FaikoutDeviceTracker
from .ota.client import FaikoutOtaClient

PLATFORMS = [Platform.BINARY_SENSOR]


@dataclass
class FaikoutRuntimeData:
    coordinator: FaikoutCoordinator
    tracker: FaikoutDeviceTracker


type FaikoutConfigEntry = ConfigEntry[FaikoutRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FaikoutConfigEntry) -> bool:
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT is not available")

    channel = Channel(entry.options.get(CONF_CHANNEL, entry.data[CONF_CHANNEL]))
    client = FaikoutOtaClient(async_get_clientsession(hass))
    coordinator = FaikoutCoordinator(hass, client, channel)
    tracker = FaikoutDeviceTracker(hass)

    await tracker.async_start()
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await tracker.async_stop()
        raise

    entry.runtime_data = FaikoutRuntimeData(coordinator, tracker)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FaikoutConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.tracker.async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: FaikoutConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
