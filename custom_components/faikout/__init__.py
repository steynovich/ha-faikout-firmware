"""The Faikout Firmware Update integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_CHANNEL, DOMAIN, Channel
from .coordinator import FaikoutCoordinator
from .device_tracker import FaikoutDeviceTracker
from .ota.client import FaikoutOtaClient

PLATFORMS = [Platform.BINARY_SENSOR]


@dataclass
class FaikoutRuntimeData:
    coordinator: FaikoutCoordinator
    tracker: FaikoutDeviceTracker


type FaikoutConfigEntry = ConfigEntry[FaikoutRuntimeData]


async def async_migrate_entry(hass: HomeAssistant, entry: FaikoutConfigEntry) -> bool:
    if entry.version > 2:
        # Written by a newer release of this integration; refuse rather than guess.
        return False
    if entry.version == 1:
        # v1 wrote the channel to entry.data at creation and to entry.options on
        # change, so every reader had to consult both. Collapse onto options,
        # preferring the options value because it is the one the user last chose.
        data = dict(entry.data)
        stale_channel = data.pop(CONF_CHANNEL, Channel.STABLE.value)
        channel = entry.options.get(CONF_CHANNEL, stale_channel)
        hass.config_entries.async_update_entry(
            entry, data=data, options={**entry.options, CONF_CHANNEL: channel}, version=2
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FaikoutConfigEntry) -> bool:
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="mqtt_unavailable")

    channel = Channel(entry.options.get(CONF_CHANNEL, Channel.STABLE.value))
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


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: FaikoutConfigEntry, device: DeviceEntry
) -> bool:
    # Faikout devices are known only from live MQTT state messages; there is no
    # reliable "device gone" signal, so a device that stops reporting lingers in
    # the registry. Allow the user to delete such stale devices manually.
    return True
