"""Diagnostics support for the Faikout Firmware Update integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import FaikoutConfigEntry

TO_REDACT = {"id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FaikoutConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "channel": data.coordinator.channel.value,
        "latest_versions": data.coordinator.data,
        "devices": [
            async_redact_data(asdict(device), TO_REDACT) for device in data.tracker.devices.values()
        ],
    }
