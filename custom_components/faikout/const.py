"""Constants for the Faikout Firmware Update integration."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

DOMAIN = "faikout"
CONF_CHANNEL = "channel"
STATE_PREFIX = "state/"
UPDATE_INTERVAL = timedelta(hours=3)
SIGNAL_DEVICE_UPDATE = "faikout_device_update"
MANUFACTURER = "RevK"


class Channel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


MANIFEST_URLS: dict[tuple[str, Channel], str] = {
    # The stable channel is published as the unversioned "Faikout.manifest"; the
    # per-target "Faikout-S3-MINI-N4-R2-manifest.json" path 404s on the OTA server.
    ("Faikout-S3-MINI-N4-R2", Channel.STABLE): "https://ota.faikout.uk/Faikout.manifest",
    ("Faikout-S3-MINI-N4-R2", Channel.BETA): (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    ),
}
