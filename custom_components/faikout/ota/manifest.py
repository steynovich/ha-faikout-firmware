"""Parse an OTA manifest and return the application image URL."""

from __future__ import annotations

import json
from typing import Any

from .exceptions import ManifestError


def parse_manifest(data: bytes | str | dict[str, Any]) -> str:
    """Return the URL of the ``flash`` entry with ``app: true``."""
    if isinstance(data, (bytes, str)):
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ManifestError(f"manifest is not valid JSON: {err}") from err
    else:
        parsed = data

    if not isinstance(parsed, dict):
        raise ManifestError("manifest must be a JSON object")

    flash = parsed.get("flash")
    if not isinstance(flash, list) or not flash:
        raise ManifestError("manifest has no non-empty 'flash' list")

    for entry in flash:
        if isinstance(entry, dict) and entry.get("app") is True:
            url = entry.get("url")
            if not isinstance(url, str) or not url:
                raise ManifestError("app entry is missing a 'url'")
            return url

    raise ManifestError("manifest has no entry with 'app': true")
