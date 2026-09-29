import logging

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.faikout.const import Channel
from custom_components.faikout.coordinator import FaikoutCoordinator
from custom_components.faikout.ota.client import FaikoutOtaClient
from custom_components.faikout.ota.exceptions import (
    FirmwareFetchError,
    FirmwareParseError,
    FirmwareUnavailableError,
)

LOGGER = "custom_components.faikout.coordinator"
BETA_URL = "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
GOOD_URL = "https://ota.faikout.uk/good"
BAD_URL = "https://ota.faikout.uk/bad"

# Two targets on one channel, so a failure of one is a *partial* failure: the
# refresh still succeeds and DataUpdateCoordinator logs nothing of its own.
TWO_TARGETS = {
    ("Good-Target", Channel.BETA): GOOD_URL,
    ("Bad-Target", Channel.BETA): BAD_URL,
}


class StubClient:
    def __init__(self, mapping=None, error=None):
        self._mapping = mapping or {}
        self._error = error

    async def async_get_latest_version(self, manifest_url):
        if self._error:
            raise self._error
        return self._mapping[manifest_url]


class ScriptedClient:
    """Per-URL scripted outcomes, so results never depend on iteration order."""

    def __init__(self, scripts):
        self._scripts = {url: list(outcomes) for url, outcomes in scripts.items()}

    async def async_get_latest_version(self, manifest_url):
        outcome = self._scripts[manifest_url].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _records(caplog, level):
    return [r for r in caplog.records if r.levelno == level and r.name == LOGGER]


async def test_update_returns_target_to_version(hass):
    client = StubClient({BETA_URL: "1a347969"})
    coordinator = FaikoutCoordinator(hass, client, Channel.BETA)
    data = await coordinator._async_update_data()
    assert data == {"Faikout-S3-MINI-N4-R2": "1a347969"}


async def test_all_failures_raise_update_failed(hass):
    client = StubClient(error=FirmwareFetchError("down"))
    coordinator = FaikoutCoordinator(hass, client, Channel.STABLE)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_channel_with_no_manifest_urls_does_not_report_none(hass, monkeypatch):
    # With no URL for the channel the fetch loop never runs, so there is no
    # underlying error to interpolate; the message must not read "... : None".
    monkeypatch.setattr("custom_components.faikout.coordinator.MANIFEST_URLS", {})
    coordinator = FaikoutCoordinator(hass, StubClient(), Channel.STABLE)

    with pytest.raises(UpdateFailed) as excinfo:
        await coordinator._async_update_data()

    assert excinfo.value.translation_key == "no_manifest_urls"
    assert "None" not in str(excinfo.value.translation_placeholders)


async def test_total_failure_stays_quiet_and_leaves_it_to_the_base_class(hass, caplog):
    # DataUpdateCoordinator already logs a wholly-failed refresh once on the way
    # down and once on recovery; logging here too would double every outage.
    client = StubClient(error=FirmwareFetchError("down"))
    coordinator = FaikoutCoordinator(hass, client, Channel.BETA)

    with caplog.at_level(logging.DEBUG, logger=LOGGER), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert _records(caplog, logging.WARNING) == []
    assert _records(caplog, logging.INFO) == []


async def test_unreachable_target_warns_once_then_recovers_once(hass, caplog, monkeypatch):
    monkeypatch.setattr("custom_components.faikout.coordinator.MANIFEST_URLS", TWO_TARGETS)
    coordinator = FaikoutCoordinator(
        hass,
        ScriptedClient(
            {
                GOOD_URL: ["1a347969", "1a347969", "1a347969"],
                BAD_URL: [
                    FirmwareUnavailableError("no route"),
                    FirmwareUnavailableError("no route"),
                    "1a347969",
                ],
            }
        ),
        Channel.BETA,
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for _ in range(3):
            await coordinator._async_update_data()

    warnings = _records(caplog, logging.WARNING)
    recoveries = _records(caplog, logging.INFO)
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert len(recoveries) == 1, [r.getMessage() for r in recoveries]
    assert "Bad-Target" in warnings[0].getMessage()
    assert "Bad-Target" in recoveries[0].getMessage()


async def test_unusable_metadata_warns_on_every_refresh(hass, caplog, monkeypatch):
    # A malformed image is a server-side data fault; the next poll hits the same
    # bad bytes, so it must not be silenced after the first occurrence.
    monkeypatch.setattr("custom_components.faikout.coordinator.MANIFEST_URLS", TWO_TARGETS)
    coordinator = FaikoutCoordinator(
        hass,
        ScriptedClient(
            {
                GOOD_URL: ["1a347969", "1a347969"],
                BAD_URL: [FirmwareParseError("bad magic"), FirmwareParseError("bad magic")],
            }
        ),
        Channel.BETA,
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for _ in range(2):
            await coordinator._async_update_data()

    assert len(_records(caplog, logging.WARNING)) == 2


async def test_dead_url_warns_on_every_refresh(hass, caplog, monkeypatch):
    # A 404 is a broken URL, not an outage: warn-once-then-silence is exactly how
    # the dead stable-channel manifest stayed hidden, so this must repeat.
    monkeypatch.setattr("custom_components.faikout.coordinator.MANIFEST_URLS", TWO_TARGETS)
    coordinator = FaikoutCoordinator(
        hass,
        ScriptedClient(
            {
                GOOD_URL: ["1a347969", "1a347969"],
                BAD_URL: [FirmwareFetchError("status 404"), FirmwareFetchError("status 404")],
            }
        ),
        Channel.BETA,
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for _ in range(2):
            await coordinator._async_update_data()

    assert len(_records(caplog, logging.WARNING)) == 2


async def test_partial_failure_is_not_silent(hass, caplog, monkeypatch):
    monkeypatch.setattr("custom_components.faikout.coordinator.MANIFEST_URLS", TWO_TARGETS)
    coordinator = FaikoutCoordinator(
        hass,
        ScriptedClient({GOOD_URL: ["1a347969"], BAD_URL: [FirmwareUnavailableError("no route")]}),
        Channel.BETA,
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        data = await coordinator._async_update_data()

    assert data == {"Good-Target": "1a347969"}
    warnings = _records(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "Bad-Target" in warnings[0].getMessage()


async def test_undecodable_manifest_becomes_update_failed(hass):
    class UndecodableSession:
        def get(self, url, headers=None, timeout=None):
            return _UndecodableResponse()

    class _UndecodableResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        async def text(self):
            return b"\xff\xfe".decode()

    coordinator = FaikoutCoordinator(hass, FaikoutOtaClient(UndecodableSession()), Channel.BETA)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
