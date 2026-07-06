"""Constants for the Faikout Firmware Update integration."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

DOMAIN = "faikout"
CONF_CHANNEL = "channel"
DEFAULT_STATE_PREFIX = "state/"
UPDATE_INTERVAL = timedelta(hours=3)
SIGNAL_DEVICE_UPDATE = "faikout_device_update"
MANUFACTURER = "RevK"


class Channel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


MANIFEST_URLS: dict[tuple[str, Channel], str] = {
    ("Faikout-S3-MINI-N4-R2", Channel.STABLE): (
        "https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json"
    ),
    ("Faikout-S3-MINI-N4-R2", Channel.BETA): (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    ),
}


def manifest_url_for(target: str, channel: Channel) -> str | None:
    """Return the manifest URL for a target/channel, or None if unknown."""
    return MANIFEST_URLS.get((target, channel))
