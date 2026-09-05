"""DataUpdateCoordinator that tracks the latest firmware version per target."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MANIFEST_URLS, UPDATE_INTERVAL, Channel
from .ota.client import FaikoutOtaClient
from .ota.exceptions import FaikoutError, FirmwareUnavailableError

_LOGGER = logging.getLogger(__name__)


class FaikoutCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Fetch the latest available firmware version for each known target."""

    def __init__(self, hass: HomeAssistant, client: FaikoutOtaClient, channel: Channel) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self._client = client
        self.channel = channel
        # Targets already warned about as an unreachable-server outage, so the
        # warning lands once on the way down and a recovery lands once on the way up.
        self._unreachable_targets: set[str] = set()

    async def _async_update_data(self) -> dict[str, str]:
        # Iterate ALL entries in MANIFEST_URLS for this channel, not just targets seen
        # among tracked devices, so async_config_entry_first_refresh() validates OTA
        # connectivity even before any device has reported over MQTT. A FaikoutError
        # only becomes an UpdateFailed when NO target could be fetched at all: both
        # transient network errors and permanent data faults are treated as retryable
        # here, since a server-side data fault may later be corrected server-side.
        result: dict[str, str] = {}
        failures: dict[str, FaikoutError] = {}
        for (target, channel), url in MANIFEST_URLS.items():
            if channel != self.channel:
                continue
            try:
                result[target] = await self._client.async_get_latest_version(url)
            except FaikoutError as error:
                # Safe to keep past the except block: only the name is unbound.
                failures[target] = error

        if not result:
            # Every target failed, which DataUpdateCoordinator already logs once on
            # the way down and once on recovery. Stay quiet so the outage is not
            # reported twice; just carry the state so a later partial failure is
            # still judged against it.
            self._unreachable_targets = {
                target
                for target, err in failures.items()
                if isinstance(err, FirmwareUnavailableError)
            }
            last_error = next(iter(failures.values()), None)
            if last_error is None:
                # The loop never ran: no manifest URL is mapped for this channel, so
                # there is no underlying error to report and retrying cannot help.
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="no_manifest_urls",
                    translation_placeholders={"channel": self.channel.value},
                )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_fetch_version",
                translation_placeholders={"error": str(last_error)},
            )

        # Some targets resolved, so the refresh counts as a success and the base
        # class logs nothing. Report the stragglers here or they stay invisible.
        for target, err in failures.items():
            self._log_target_failed(target, err)
        for target in result:
            self._log_target_recovered(target)
        return result

    def _log_target_failed(self, target: str, err: FaikoutError) -> None:
        if not isinstance(err, FirmwareUnavailableError):
            # A 404, a malformed manifest or a bad image will not clear itself on
            # the next poll, and staying quiet is how a dead stable-channel URL
            # went unnoticed for two months. Say so every time.
            self._unreachable_targets.discard(target)
            _LOGGER.warning("Firmware metadata for %s is unusable: %s", target, err)
        elif target in self._unreachable_targets:
            _LOGGER.debug("OTA server still unreachable for %s: %s", target, err)
        else:
            self._unreachable_targets.add(target)
            _LOGGER.warning("Cannot reach the OTA server for %s: %s", target, err)

    def _log_target_recovered(self, target: str) -> None:
        if target in self._unreachable_targets:
            self._unreachable_targets.discard(target)
            _LOGGER.info("OTA server reachable again for %s", target)
