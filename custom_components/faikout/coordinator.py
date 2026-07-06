"""DataUpdateCoordinator that tracks the latest firmware version per target."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MANIFEST_URLS, UPDATE_INTERVAL, Channel
from .ota.client import FaikoutOtaClient
from .ota.exceptions import FaikoutError

_LOGGER = logging.getLogger(__name__)


class FaikoutCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Fetch the latest available firmware version for each known target."""

    def __init__(self, hass: HomeAssistant, client: FaikoutOtaClient, channel: Channel) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self._client = client
        self.channel = channel

    async def _async_update_data(self) -> dict[str, str]:
        result: dict[str, str] = {}
        last_error: Exception | None = None
        for (target, channel), url in MANIFEST_URLS.items():
            if channel != self.channel:
                continue
            try:
                result[target] = await self._client.async_get_latest_version(url)
            except FaikoutError as err:
                last_error = err
                _LOGGER.debug("Failed to fetch latest version for %s: %s", target, err)
        if not result:
            raise UpdateFailed(f"no firmware versions could be fetched: {last_error}")
        return result
