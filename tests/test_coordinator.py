import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.faikout.const import Channel
from custom_components.faikout.coordinator import FaikoutCoordinator
from custom_components.faikout.ota.exceptions import FirmwareFetchError


class StubClient:
    def __init__(self, mapping=None, error=None):
        self._mapping = mapping or {}
        self._error = error

    async def async_get_latest_version(self, manifest_url):
        if self._error:
            raise self._error
        return self._mapping[manifest_url]


async def test_update_returns_target_to_version(hass):
    client = StubClient(
        {
            "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json": "1a347969",
        }
    )
    coordinator = FaikoutCoordinator(hass, client, Channel.BETA)
    data = await coordinator._async_update_data()
    assert data == {"Faikout-S3-MINI-N4-R2": "1a347969"}


async def test_all_failures_raise_update_failed(hass):
    client = StubClient(error=FirmwareFetchError("down"))
    coordinator = FaikoutCoordinator(hass, client, Channel.STABLE)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
