"""Firmware-update-available binary sensor for each Faikout device."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FaikoutConfigEntry
from .const import CONF_CHANNEL, DOMAIN, MANUFACTURER, SIGNAL_DEVICE_UPDATE
from .coordinator import FaikoutCoordinator
from .device_tracker import FaikoutDeviceTracker

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FaikoutConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add(device_id: str) -> None:
        if device_id in known or device_id not in data.tracker.devices:
            return
        known.add(device_id)
        async_add_entities(
            [FirmwareUpdateBinarySensor(data.coordinator, data.tracker, entry, device_id)]
        )

    for device_id in list(data.tracker.devices):
        _add(device_id)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATE, _add))


class FirmwareUpdateBinarySensor(CoordinatorEntity[FaikoutCoordinator], BinarySensorEntity):
    """Reports whether a firmware update is available for one device."""

    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_has_entity_name = True
    _attr_name = "Firmware update"

    def __init__(
        self,
        coordinator: FaikoutCoordinator,
        tracker: FaikoutDeviceTracker,
        entry: FaikoutConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._tracker = tracker
        self._entry = entry
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_firmware_update"
        device = tracker.devices[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(device_id))},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=device.target,
        )

    @property
    def _latest(self) -> str | None:
        device = self._tracker.devices.get(self._device_id)
        if device is None:
            return None
        return self.coordinator.data.get(device.target)

    @property
    def available(self) -> bool:
        device = self._tracker.devices.get(self._device_id)
        return super().available and device is not None and self._latest is not None

    @property
    def is_on(self) -> bool | None:
        device = self._tracker.devices.get(self._device_id)
        latest = self._latest
        if device is None or latest is None:
            return None
        return device.version != latest

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        device = self._tracker.devices.get(self._device_id)
        return {
            "installed_version": device.version if device else None,
            "latest_version": self._latest,
            "channel": self._entry.options.get(CONF_CHANNEL, self._entry.data[CONF_CHANNEL]),
            "target": device.target if device else None,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_DEVICE_UPDATE, self._handle_device_update)
        )

    @callback
    def _handle_device_update(self, device_id: str) -> None:
        if device_id == self._device_id:
            self.async_write_ha_state()
