# Faikout Firmware Update Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-installable Home Assistant custom integration (`faikout`) that adds one "firmware update available" `binary_sensor` per Faikout device, comparing the device's MQTT-reported installed version against the latest version on the OTA server for the selected channel.

**Architecture:** A pure/async OTA core (`custom_components/faikout/ota/`) fetches the latest version (manifest → `app:true` image → `esp_app_desc_t`). A `DataUpdateCoordinator` polls it per target/channel. A `FaikoutDeviceTracker` subscribes to the Faikout MQTT state topics to learn each device's installed version and target. A `binary_sensor` (`device_class: update`) per device combines the two.

**Tech Stack:** Python >=3.13, Home Assistant, aiohttp (from HA), MQTT (HA dependency), uv, pytest + pytest-homeassistant-custom-component, ruff, mypy.

## Global Constraints

- Integration domain: `faikout`. Layout: `custom_components/faikout/`. HACS category: integration.
- The OTA core under `custom_components/faikout/ota/` imports **only** `aiohttp` — no Home Assistant imports — so it stays pure and unit-testable.
- Never hardcode the app image `.bin` URL — always follow the manifest's `app: true` entry.
- `(target, channel) → manifest URL` is a lookup table; unknown target → sensor `unavailable`, never a guessed URL.
  - `("Faikout-S3-MINI-N4-R2", stable)` → `https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json`
  - `("Faikout-S3-MINI-N4-R2", beta)` → `https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json`
- ESP-IDF app descriptor magic word `0xABCD5432` (little-endian on disk); `version` is a 32-byte null-padded string at +16 from the magic.
- Installed version and target come from the device MQTT state payload: `version`, and `app` + `build-suffix` (target = `app + build-suffix`). Compare with exact string equality.
- OTA fetch: first 512 bytes via HTTP Range (full-GET fallback); `request_timeout` default 30 s; wrap `aiohttp.ClientError`/`TimeoutError`/bad status in `FirmwareFetchError`; never close the injected session.

**Quality bar — Home Assistant Silver (applicable rules):**
- `manifest.json` with `version`, `codeowners`, `iot_class`, `config_flow: true`, `dependencies: ["mqtt"]`; `hacs.json`; MIT `LICENSE`; CI running hassfest + HACS validation + tests.
- `ruff` clean; `mypy` clean (strict on the `ota` subpackage); **≥95% coverage** on the non-network suite.
- `runtime-data`, `config-entry-unloading` (unload unsubscribes MQTT), `unique-config-entry` (single instance), `appropriate-polling` (3 h), `test-before-setup` (`async_config_entry_first_refresh`), `entity-unavailable` + `log-when-unavailable`, `PARALLEL_UPDATES = 0`.

---

### Task 1: Repo scaffold (HACS layout, tooling, CI)

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `hacs.json`, `README.md`, `.gitignore` (already exists — leave)
- Create: `custom_components/faikout/manifest.json`
- Create: `custom_components/faikout/__init__.py` (temporary stub)
- Create: `tests/__init__.py`, `tests/conftest.py`
- Create: `.github/workflows/ci.yml`, `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: an environment where `uv run pytest`, `uv run ruff check .`, and `uv run mypy` run; a HA-loadable (empty) integration; CI that validates HACS + hassfest.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "faikout-hacs"
version = "0.1.0"
description = "Home Assistant integration: firmware-update-available sensor for Faikout devices."
readme = "README.md"
requires-python = ">=3.13"
license = "MIT"
license-files = ["LICENSE"]

[dependency-groups]
dev = [
    "pytest-homeassistant-custom-component>=0.13",
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["network: tests that hit the live OTA server (skipped when offline)"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.13"
disallow_untyped_defs = true
warn_unused_ignores = true
warn_return_any = true
files = ["custom_components/faikout"]

[[tool.mypy.overrides]]
module = "custom_components.faikout.ota.*"
strict = true

[tool.coverage.run]
branch = true
source = ["custom_components/faikout"]

[tool.coverage.report]
show_missing = true
```

- [ ] **Step 2: Create `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 Faikout contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Create `hacs.json`**

```json
{
  "name": "Faikout Firmware Update",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
```

- [ ] **Step 4: Create `custom_components/faikout/manifest.json`**

```json
{
  "domain": "faikout",
  "name": "Faikout Firmware Update",
  "codeowners": ["@steyn"],
  "config_flow": true,
  "dependencies": ["mqtt"],
  "documentation": "https://github.com/steyn/faikout",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/steyn/faikout/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 5: Create stubs and test harness**

`custom_components/faikout/__init__.py`:

```python
"""The Faikout Firmware Update integration."""
```

`tests/__init__.py` — empty file.

`tests/conftest.py`:

```python
"""Shared test fixtures."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield
```

`README.md`:

````markdown
# Faikout Firmware Update

A Home Assistant custom integration (HACS) that adds a **firmware-update-available**
`binary_sensor` to each Faikout device. It reads each device's installed firmware
version from MQTT and compares it against the latest version published on the
Faikout OTA server for the channel you select (stable or beta). Notification only —
it does not flash firmware.

## Install (HACS)

Add this repository as a custom repository (category: Integration), install, then
add the **Faikout Firmware Update** integration and pick a channel.

## Requirements

- The Home Assistant **MQTT** integration, with Faikout (RevK) devices already
  discovered (they publish `state/<hostname>` with `version` and `build-suffix`).

## Entities

Per device: `binary_sensor.<device>_firmware_update` — `on` when an update is
available. Attributes: `installed_version`, `latest_version`, `channel`, `target`.
````

- [ ] **Step 6: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.13"
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy
      - run: uv run pytest -m "not network" --cov --cov-report=term-missing --cov-fail-under=95
```

- [ ] **Step 7: Create `.github/workflows/validate.yml`**

```yaml
name: Validate
on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master
  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
```

- [ ] **Step 8: Sync and verify tooling**

Run: `uv python pin 3.13 && uv sync && uv run ruff check . && uv run pytest -q`
Expected: environment resolves (pulls in `homeassistant` via the test harness); ruff clean; pytest reports "no tests ran" (exit 5) or 0 tests — acceptable at this stage.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .python-version LICENSE hacs.json README.md \
  custom_components/faikout/manifest.json custom_components/faikout/__init__.py \
  tests/__init__.py tests/conftest.py .github/workflows/ci.yml .github/workflows/validate.yml
git commit -m "chore: scaffold Faikout HACS integration with tooling and CI"
```

---

### Task 2: Constants and OTA exceptions

**Files:**
- Create: `custom_components/faikout/const.py`
- Create: `custom_components/faikout/ota/__init__.py`
- Create: `custom_components/faikout/ota/exceptions.py`
- Test: `tests/test_const.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `const.py`: `DOMAIN = "faikout"`, `CONF_CHANNEL = "channel"`, `DEFAULT_STATE_PREFIX = "state/"`, `UPDATE_INTERVAL = timedelta(hours=3)`, `SIGNAL_DEVICE_UPDATE = "faikout_device_update"`, `MANUFACTURER = "RevK"`, `class Channel(StrEnum)` (`STABLE="stable"`, `BETA="beta"`), `MANIFEST_URLS: dict[tuple[str, Channel], str]`, and `manifest_url_for(target: str, channel: Channel) -> str | None`.
  - `ota/exceptions.py`: `FaikoutError` (base) → `ManifestError`, `FirmwareParseError`, `FirmwareFetchError`.

- [ ] **Step 1: Write the failing test**

`tests/test_const.py`:

```python
from custom_components.faikout.const import (
    Channel, manifest_url_for, MANIFEST_URLS, DOMAIN,
)
from custom_components.faikout.ota.exceptions import (
    FaikoutError, ManifestError, FirmwareParseError, FirmwareFetchError,
)


def test_domain():
    assert DOMAIN == "faikout"


def test_channel_values():
    assert Channel.STABLE == "stable"
    assert Channel.BETA == "beta"


def test_manifest_url_for_known_target():
    assert manifest_url_for("Faikout-S3-MINI-N4-R2", Channel.STABLE) == (
        "https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json"
    )
    assert manifest_url_for("Faikout-S3-MINI-N4-R2", Channel.BETA) == (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    )


def test_manifest_url_for_unknown_target_returns_none():
    assert manifest_url_for("Nope-X1", Channel.BETA) is None


def test_exception_hierarchy():
    for exc in (ManifestError, FirmwareParseError, FirmwareFetchError):
        assert issubclass(exc, FaikoutError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_const.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.const'`.

- [ ] **Step 3: Write `ota/__init__.py` and `ota/exceptions.py`**

`custom_components/faikout/ota/__init__.py`:

```python
"""Pure/async OTA fetch core (no Home Assistant imports)."""
```

`custom_components/faikout/ota/exceptions.py`:

```python
"""Exception hierarchy for the OTA core."""


class FaikoutError(Exception):
    """Base class for all Faikout OTA errors."""


class ManifestError(FaikoutError):
    """The OTA manifest was missing, malformed, or had no app entry."""


class FirmwareParseError(FaikoutError):
    """The firmware image did not contain a valid ESP-IDF app descriptor."""


class FirmwareFetchError(FaikoutError):
    """A network request to the OTA server failed."""
```

- [ ] **Step 4: Write `const.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_const.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add custom_components/faikout/const.py custom_components/faikout/ota/__init__.py \
  custom_components/faikout/ota/exceptions.py tests/test_const.py
git commit -m "feat: add constants, channel/URL map, and OTA exceptions"
```

---

### Task 3: OTA manifest parser

**Files:**
- Create: `custom_components/faikout/ota/manifest.py`
- Test: `tests/test_ota_manifest.py`

**Interfaces:**
- Consumes: `ManifestError`.
- Produces: `parse_manifest(data: bytes | str | dict) -> str` — the `app: true` entry's URL. Raises `ManifestError` on invalid JSON, non-object payload, missing/empty `flash`, no `app: true` entry, or an app entry without a `url`.

- [ ] **Step 1: Write the failing test**

`tests/test_ota_manifest.py`:

```python
import json

import pytest

from custom_components.faikout.ota.exceptions import ManifestError
from custom_components.faikout.ota.manifest import parse_manifest

VALID = {
    "flash": [
        {"url": "https://ota.faikout.uk/boot.bin"},
        {"address": "8000", "url": "https://ota.faikout.uk/part.bin"},
        {"address": "10000", "url": "https://ota.faikout.uk/app.bin", "app": True},
    ]
}


def test_returns_app_url_from_dict():
    assert parse_manifest(VALID) == "https://ota.faikout.uk/app.bin"


def test_returns_app_url_from_bytes():
    assert parse_manifest(json.dumps(VALID).encode()) == "https://ota.faikout.uk/app.bin"


def test_invalid_json_raises():
    with pytest.raises(ManifestError):
        parse_manifest(b"not json{")


def test_no_app_entry_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"flash": [{"url": "https://ota.faikout.uk/boot.bin"}]})


def test_missing_flash_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "Faikout"})


def test_app_entry_without_url_raises():
    with pytest.raises(ManifestError):
        parse_manifest({"flash": [{"address": "10000", "app": True}]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ota_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.ota.manifest'`.

- [ ] **Step 3: Write `ota/manifest.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ota_manifest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/ota/manifest.py tests/test_ota_manifest.py
git commit -m "feat: parse OTA manifest to app image URL"
```

---

### Task 4: ESP-IDF app descriptor parser

**Files:**
- Create: `custom_components/faikout/ota/parser.py`
- Test: `tests/test_ota_parser.py`

**Interfaces:**
- Consumes: `FirmwareParseError`.
- Produces: `parse_app_descriptor(head: bytes) -> str` — the version string. Locates magic `0xABCD5432` (bytes `52 54 CD AB`), reads the 32-byte null-padded `version` field at magic+16. Raises `FirmwareParseError` if the magic is absent or the buffer is truncated before magic+48.

- [ ] **Step 1: Write the failing test**

`tests/test_ota_parser.py`:

```python
import struct

import pytest

from custom_components.faikout.ota.exceptions import FirmwareParseError
from custom_components.faikout.ota.parser import parse_app_descriptor

MAGIC = 0xABCD5432


def _descriptor(version="1a347969"):
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += version.encode("ascii").ljust(32, b"\x00")   # version[32]
    body += b"Faikout".ljust(32, b"\x00")                # project_name[32]
    return body


def test_parses_version_at_offset_zero():
    assert parse_app_descriptor(_descriptor()) == "1a347969"


def test_finds_descriptor_after_image_header():
    head = b"\xe9\x07\x02\x20" + b"\x11" * 28 + _descriptor()
    assert parse_app_descriptor(head) == "1a347969"


def test_missing_magic_raises():
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(b"\x00" * 512)


def test_truncated_after_magic_raises():
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(_descriptor()[:30])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ota_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.ota.parser'`.

- [ ] **Step 3: Write `ota/parser.py`**

```python
"""Extract the version string from an ESP-IDF esp_app_desc_t struct."""

from __future__ import annotations

import struct

from .exceptions import FirmwareParseError

_MAGIC_BYTES = struct.pack("<I", 0xABCD5432)  # b"\x52\x54\xcd\xab"
_VERSION_OFF = 16
_VERSION_LEN = 32


def parse_app_descriptor(head: bytes) -> str:
    """Return the firmware version located via the app descriptor magic word."""
    base = head.find(_MAGIC_BYTES)
    if base == -1:
        raise FirmwareParseError("app descriptor magic word 0xABCD5432 not found")
    start = base + _VERSION_OFF
    end = start + _VERSION_LEN
    if len(head) < end:
        raise FirmwareParseError("firmware head truncated before version field")
    raw = head[start:end]
    version = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if not version:
        raise FirmwareParseError("app descriptor version field is empty")
    return version
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ota_parser.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/ota/parser.py tests/test_ota_parser.py
git commit -m "feat: parse ESP-IDF app descriptor version"
```

---

### Task 5: Async OTA client

**Files:**
- Create: `custom_components/faikout/ota/client.py`
- Test: `tests/test_ota_client.py`

**Interfaces:**
- Consumes: `parse_manifest`, `parse_app_descriptor`, `FirmwareFetchError`.
- Produces:
  - Module constants `HEAD_BYTES = 512`, `DEFAULT_TIMEOUT = 30.0`.
  - `class FaikoutOtaClient` with `__init__(self, session: aiohttp.ClientSession, *, request_timeout: float = DEFAULT_TIMEOUT)` and `async def async_get_latest_version(self, manifest_url: str) -> str`.
  - Flow: GET manifest text → `parse_manifest` → GET app image with `Range: bytes=0-511`; if status != 206 re-slice `[:HEAD_BYTES]` → `parse_app_descriptor`. Every request passes `timeout=aiohttp.ClientTimeout(total=request_timeout)`. Wrap `aiohttp.ClientError`, `TimeoutError`, and bad status in `FirmwareFetchError`. Never close the session.

- [ ] **Step 1: Write the failing test**

`tests/test_ota_client.py`:

```python
import struct

import aiohttp
import pytest

from custom_components.faikout.ota.client import FaikoutOtaClient, HEAD_BYTES
from custom_components.faikout.ota.exceptions import FirmwareFetchError

MAGIC = 0xABCD5432
MANIFEST = b'{"flash":[{"url":"https://x/app.bin","app":true}]}'


def _app_head():
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += b"1a347969".ljust(32, b"\x00") + b"Faikout".ljust(32, b"\x00")
    return body.ljust(HEAD_BYTES, b"\x00")


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode()

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientError(f"status {self.status}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_happy_path_uses_range():
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(206, _app_head())])
    client = FaikoutOtaClient(session)
    version = await client.async_get_latest_version("https://m/manifest.json")

    assert version == "1a347969"
    assert session.calls[0][0] == "https://m/manifest.json"
    assert session.calls[1][0] == "https://x/app.bin"
    assert session.calls[1][1]["Range"] == "bytes=0-511"
    assert session.calls[1][2].total == 30.0
    assert session.closed is False


@pytest.mark.asyncio
async def test_full_get_fallback_when_range_ignored():
    full = b"\x00" * 32 + _app_head()
    session = FakeSession([FakeResponse(200, MANIFEST), FakeResponse(200, full)])
    client = FaikoutOtaClient(session)
    assert await client.async_get_latest_version("https://m") == "1a347969"


@pytest.mark.asyncio
async def test_network_error_wrapped():
    class BoomSession:
        def get(self, url, headers=None, timeout=None):
            raise aiohttp.ClientError("boom")

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(BoomSession()).async_get_latest_version("https://m")


@pytest.mark.asyncio
async def test_timeout_wrapped():
    class TimeoutSession:
        def get(self, url, headers=None, timeout=None):
            raise TimeoutError

    with pytest.raises(FirmwareFetchError):
        await FaikoutOtaClient(TimeoutSession()).async_get_latest_version("https://m")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ota_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.ota.client'`.

- [ ] **Step 3: Write `ota/client.py`**

```python
"""Async aiohttp client that resolves the latest firmware version."""

from __future__ import annotations

import aiohttp

from .exceptions import FirmwareFetchError
from .manifest import parse_manifest
from .parser import parse_app_descriptor

HEAD_BYTES = 512
DEFAULT_TIMEOUT = 30.0


class FaikoutOtaClient:
    """Fetch and parse the latest Faikout firmware version.

    The aiohttp session is injected and never closed by this client.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)

    async def async_get_latest_version(self, manifest_url: str) -> str:
        manifest_text = await self._get_text(manifest_url)
        app_url = parse_manifest(manifest_text)
        head = await self._get_head(app_url)
        return parse_app_descriptor(head)

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err

    async def _get_head(self, url: str) -> bytes:
        headers = {"Range": f"bytes=0-{HEAD_BYTES - 1}"}
        try:
            async with self._session.get(
                url, headers=headers, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                body = await resp.read()
                if resp.status == 206:
                    return body
                return body[:HEAD_BYTES]
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ota_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/ota/client.py tests/test_ota_client.py
git commit -m "feat: add async OTA client with Range fetch and timeouts"
```

---

### Task 6: Firmware-update coordinator

**Files:**
- Create: `custom_components/faikout/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `FaikoutOtaClient`, `FaikoutError`, `Channel`, `MANIFEST_URLS`, `UPDATE_INTERVAL`, `DOMAIN`.
- Produces: `class FaikoutCoordinator(DataUpdateCoordinator[dict[str, str]])` with `__init__(self, hass, client: FaikoutOtaClient, channel: Channel)`. `_async_update_data` fetches the latest version for every target that has a URL for `channel`, returning `{target: version}`. Raises `UpdateFailed` if **all** fetches fail (`log-when-unavailable` handled by the coordinator's built-in logging). Partial success returns the successful subset.

- [ ] **Step 1: Write the failing test**

`tests/test_coordinator.py`:

```python
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
    client = StubClient({
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json": "1a347969",
    })
    coordinator = FaikoutCoordinator(hass, client, Channel.BETA)
    data = await coordinator._async_update_data()
    assert data == {"Faikout-S3-MINI-N4-R2": "1a347969"}


async def test_all_failures_raise_update_failed(hass):
    client = StubClient(error=FirmwareFetchError("down"))
    coordinator = FaikoutCoordinator(hass, client, Channel.STABLE)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coordinator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.coordinator'`.

- [ ] **Step 3: Write `coordinator.py`**

```python
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

    def __init__(
        self, hass: HomeAssistant, client: FaikoutOtaClient, channel: Channel
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coordinator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/coordinator.py tests/test_coordinator.py
git commit -m "feat: add firmware-version coordinator"
```

---

### Task 7: MQTT device tracker

**Files:**
- Create: `custom_components/faikout/device_tracker.py`
- Test: `tests/test_device_tracker.py`

**Interfaces:**
- Consumes: `DEFAULT_STATE_PREFIX`, `SIGNAL_DEVICE_UPDATE`; `homeassistant.components.mqtt`, `async_dispatcher_send`.
- Produces:
  - `@dataclass(frozen=True) class FaikoutDevice`: `id: str`, `name: str`, `version: str`, `target: str`.
  - `def parse_state_payload(topic: str, payload: str, *, prefix: str = DEFAULT_STATE_PREFIX) -> FaikoutDevice | None` — returns a device for Faikout state JSON (`app == "Faikout"` with string `id`, `version`, `build-suffix`), else `None`. `target = app + build-suffix`; `name = topic removeprefix prefix`.
  - `class FaikoutDeviceTracker`: `__init__(self, hass, *, prefix=DEFAULT_STATE_PREFIX)`; attribute `devices: dict[str, FaikoutDevice]`; `async def async_start()` (subscribes to `f"{prefix}+"`); `async def async_stop()` (unsubscribes). On a message that parses to a device, stores it and fires `async_dispatcher_send(hass, SIGNAL_DEVICE_UPDATE, device.id)`.

- [ ] **Step 1: Write the failing test (pure parser + tracker via mqtt mock)**

`tests/test_device_tracker.py`:

```python
import json

from custom_components.faikout.device_tracker import (
    FaikoutDevice, FaikoutDeviceTracker, parse_state_payload,
)

STATE = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
    "build-suffix": "-S3-MINI-N4-R2", "temp": 25.08,
})


def test_parse_state_payload_ok():
    dev = parse_state_payload("state/faikout_zolder", STATE)
    assert dev == FaikoutDevice(
        id="24587CDB4CC8", name="faikout_zolder",
        version="1a347969", target="Faikout-S3-MINI-N4-R2",
    )


def test_parse_ignores_non_faikout():
    assert parse_state_payload("state/other", json.dumps({"app": "Other"})) is None


def test_parse_ignores_bad_json():
    assert parse_state_payload("state/x", "not json{") is None


def test_parse_ignores_missing_fields():
    assert parse_state_payload("state/x", json.dumps({"app": "Faikout"})) is None


async def test_tracker_records_device(hass, mqtt_mock):
    tracker = FaikoutDeviceTracker(hass)
    await tracker.async_start()
    from homeassistant.components.mqtt import async_publish
    async_publish(hass, "state/faikout_zolder", STATE)
    await hass.async_block_till_done()
    assert tracker.devices["24587CDB4CC8"].version == "1a347969"
    await tracker.async_stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_device_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.faikout.device_tracker'`.

- [ ] **Step 3: Write `device_tracker.py`**

```python
"""Track Faikout devices and their installed firmware version via MQTT."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DEFAULT_STATE_PREFIX, SIGNAL_DEVICE_UPDATE

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaikoutDevice:
    id: str
    name: str
    version: str
    target: str


def parse_state_payload(
    topic: str, payload: str, *, prefix: str = DEFAULT_STATE_PREFIX
) -> FaikoutDevice | None:
    """Parse a Faikout MQTT state payload into a FaikoutDevice, or None."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("app") != "Faikout":
        return None
    dev_id = data.get("id")
    version = data.get("version")
    suffix = data.get("build-suffix")
    if not (
        isinstance(dev_id, str) and isinstance(version, str) and isinstance(suffix, str)
    ):
        return None
    name = topic[len(prefix):] if topic.startswith(prefix) else topic
    return FaikoutDevice(
        id=dev_id, name=name, version=version, target=f"Faikout{suffix}"
    )


class FaikoutDeviceTracker:
    """Subscribe to Faikout state topics and maintain a device map."""

    def __init__(
        self, hass: HomeAssistant, *, prefix: str = DEFAULT_STATE_PREFIX
    ) -> None:
        self._hass = hass
        self._prefix = prefix
        self.devices: dict[str, FaikoutDevice] = {}
        self._unsub: callable | None = None

    async def async_start(self) -> None:
        self._unsub = await mqtt.async_subscribe(
            self._hass, f"{self._prefix}+", self._handle_message, qos=0
        )

    async def async_stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_message(self, msg: mqtt.ReceiveMessage) -> None:
        device = parse_state_payload(msg.topic, msg.payload, prefix=self._prefix)
        if device is None:
            return
        previous = self.devices.get(device.id)
        self.devices[device.id] = device
        if previous != device:
            async_dispatcher_send(self._hass, SIGNAL_DEVICE_UPDATE, device.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device_tracker.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/device_tracker.py tests/test_device_tracker.py
git commit -m "feat: track Faikout devices and versions over MQTT"
```

---

### Task 8: Config flow

**Files:**
- Create: `custom_components/faikout/config_flow.py`
- Create: `custom_components/faikout/strings.json`
- Create: `custom_components/faikout/translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `DOMAIN`, `CONF_CHANNEL`, `Channel`.
- Produces:
  - `class FaikoutConfigFlow(ConfigFlow, domain=DOMAIN)` with `async_step_user`: aborts `single_instance_allowed` if an entry exists; otherwise shows a form selecting `channel` (default `stable`) and creates an entry titled "Faikout Firmware Update" with `{CONF_CHANNEL: <value>}`.
  - `class FaikoutOptionsFlow` allowing the channel to be changed; stored in `entry.options`.
  - `async_get_options_flow` static method returning the options flow.

- [ ] **Step 1: Write the failing test**

`tests/test_config_flow.py`:

```python
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHANNEL: "beta"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CHANNEL: "beta"}


async def test_single_instance(hass):
    MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "stable"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: FAIL — flow handler not registered / module missing.

- [ ] **Step 3: Write `config_flow.py`**

```python
"""Config and options flow for the Faikout Firmware Update integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import CONF_CHANNEL, DOMAIN, Channel

_CHANNELS = [c.value for c in Channel]


class FaikoutConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title="Faikout Firmware Update", data=user_input
            )
        schema = vol.Schema(
            {vol.Required(CONF_CHANNEL, default=Channel.STABLE.value): vol.In(_CHANNELS)}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FaikoutOptionsFlow()


class FaikoutOptionsFlow(OptionsFlow):
    """Allow changing the channel after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_CHANNEL, self.config_entry.data.get(CONF_CHANNEL, Channel.STABLE.value)
        )
        schema = vol.Schema(
            {vol.Required(CONF_CHANNEL, default=current): vol.In(_CHANNELS)}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
```

- [ ] **Step 4: Write `strings.json` and `translations/en.json` (identical content)**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Faikout Firmware Update",
        "description": "Choose which firmware channel to monitor.",
        "data": { "channel": "Channel" }
      }
    },
    "abort": {
      "single_instance_allowed": "Already configured. Only a single configuration is possible."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Faikout Firmware Update",
        "data": { "channel": "Channel" }
      }
    }
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add custom_components/faikout/config_flow.py custom_components/faikout/strings.json \
  custom_components/faikout/translations/en.json tests/test_config_flow.py
git commit -m "feat: add config and options flow"
```

---

### Task 9: Entry setup and unload wiring

**Files:**
- Modify: `custom_components/faikout/__init__.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `Channel`, `CONF_CHANNEL`, `FaikoutCoordinator`, `FaikoutDeviceTracker`, `FaikoutOtaClient`; HA `Platform`, `async_get_clientsession`, `mqtt.async_wait_for_mqtt_client`.
- Produces:
  - `PLATFORMS = [Platform.BINARY_SENSOR]`.
  - `@dataclass class FaikoutRuntimeData`: `coordinator: FaikoutCoordinator`, `tracker: FaikoutDeviceTracker`. Type alias `FaikoutConfigEntry = ConfigEntry[FaikoutRuntimeData]`.
  - `async def async_setup_entry(hass, entry) -> bool`: wait for MQTT (`ConfigEntryNotReady` if unavailable) → build client (shared session), coordinator, tracker → `tracker.async_start()` → `coordinator.async_config_entry_first_refresh()` (on failure, stop tracker and re-raise) → store on `entry.runtime_data` → forward `PLATFORMS` → register options-update reload listener.
  - `async def async_unload_entry(hass, entry) -> bool`: unload platforms; if ok, `tracker.async_stop()`.

- [ ] **Step 1: Write the failing test**

`tests/test_init.py`:

```python
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN


async def test_setup_and_unload(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.coordinator.data == {"Faikout-S3-MINI-N4-R2": "1a347969"}

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_init.py -v`
Expected: FAIL — `async_setup_entry` not defined.

- [ ] **Step 3: Rewrite `__init__.py`**

```python
"""The Faikout Firmware Update integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CHANNEL, Channel
from .coordinator import FaikoutCoordinator
from .device_tracker import FaikoutDeviceTracker
from .ota.client import FaikoutOtaClient

PLATFORMS = [Platform.BINARY_SENSOR]


@dataclass
class FaikoutRuntimeData:
    coordinator: FaikoutCoordinator
    tracker: FaikoutDeviceTracker


type FaikoutConfigEntry = ConfigEntry[FaikoutRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FaikoutConfigEntry) -> bool:
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT is not available")

    channel = Channel(
        entry.options.get(CONF_CHANNEL, entry.data[CONF_CHANNEL])
    )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_init.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/__init__.py tests/test_init.py
git commit -m "feat: wire up entry setup and unload"
```

---

### Task 10: binary_sensor platform

**Files:**
- Create: `custom_components/faikout/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: `FaikoutConfigEntry`, `FaikoutCoordinator`, `FaikoutDeviceTracker`, `CONF_CHANNEL`, `DOMAIN`, `MANUFACTURER`, `SIGNAL_DEVICE_UPDATE`.
- Produces:
  - `PARALLEL_UPDATES = 0`.
  - `async def async_setup_entry(hass, entry, async_add_entities)` — adds a `FirmwareUpdateBinarySensor` for each already-known device and, via `async_dispatcher_connect(SIGNAL_DEVICE_UPDATE)`, for each newly discovered device (dedup by id).
  - `class FirmwareUpdateBinarySensor(CoordinatorEntity[FaikoutCoordinator], BinarySensorEntity)`: `device_class = UPDATE`, `has_entity_name = True`, name "Firmware update", `unique_id = f"{id}_firmware_update"`. `is_on` = installed != latest; `available` = device present and latest known; attributes `installed_version`, `latest_version`, `channel`, `target`; `device_info` linked via `CONNECTION_NETWORK_MAC` + `(DOMAIN, id)`. Refreshes on the device dispatcher signal for its own id.

- [ ] **Step 1: Write the failing test**

`tests/test_binary_sensor.py`:

```python
import json
from unittest.mock import patch

from homeassistant.components.mqtt import async_publish
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN

STATE_OLD = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "0old0000",
    "build-suffix": "-S3-MINI-N4-R2",
})
STATE_CURRENT = json.dumps({
    "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
    "build-suffix": "-S3-MINI-N4-R2",
})


async def _setup(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "beta"})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.faikout.FaikoutOtaClient.async_get_latest_version",
        return_value="1a347969",
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_update_available_when_versions_differ(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    async_publish(hass, "state/faikout_zolder", STATE_OLD)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["installed_version"] == "0old0000"
    assert state.attributes["latest_version"] == "1a347969"


async def test_up_to_date_when_versions_match(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    async_publish(hass, "state/faikout_zolder", STATE_CURRENT)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.faikout_zolder_firmware_update")
    assert state.state == "off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_binary_sensor.py -v`
Expected: FAIL — platform/module missing; no entity created.

- [ ] **Step 3: Write `binary_sensor.py`**

```python
"""Firmware-update-available binary sensor for each Faikout device."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
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

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_UPDATE, _add)
    )


class FirmwareUpdateBinarySensor(
    CoordinatorEntity[FaikoutCoordinator], BinarySensorEntity
):
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
            "channel": self._entry.options.get(
                CONF_CHANNEL, self._entry.data[CONF_CHANNEL]
            ),
            "target": device.target if device else None,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_DEVICE_UPDATE, self._handle_device_update
            )
        )

    @callback
    def _handle_device_update(self, device_id: str) -> None:
        if device_id == self._device_id:
            self.async_write_ha_state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_binary_sensor.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/faikout/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: add firmware-update binary sensor per device"
```

---

### Task 11: Live e2e test + full quality gate

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Consumes: `FaikoutOtaClient`, `manifest_url_for`, `Channel`.
- Produces: a skippable live test per channel.

- [ ] **Step 1: Write the live test**

`tests/test_e2e.py`:

```python
import aiohttp
import pytest

from custom_components.faikout.const import Channel, manifest_url_for
from custom_components.faikout.ota.client import FaikoutOtaClient


@pytest.mark.network
@pytest.mark.parametrize("channel", [Channel.STABLE, Channel.BETA])
async def test_live_version_is_nonempty(channel):
    url = manifest_url_for("Faikout-S3-MINI-N4-R2", channel)
    try:
        async with aiohttp.ClientSession() as session:
            version = await FaikoutOtaClient(session).async_get_latest_version(url)
    except aiohttp.ClientError as err:
        pytest.skip(f"OTA server unreachable: {err}")
    assert version
```

- [ ] **Step 2: Run the full non-network gate (lint, types, coverage)**

Run:
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && \
uv run pytest -m "not network" --cov --cov-report=term-missing --cov-fail-under=95
```
Expected: ruff clean; mypy `Success`; all tests pass; coverage ≥ 95%. If coverage falls short, add targeted tests (do not lower the threshold).

- [ ] **Step 3: Run the live test (requires network)**

Run: `uv run pytest -m network -v`
Expected: PASS for both channels (or SKIP if offline).

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add skippable live e2e version check"
```

---

## Self-Review

**Spec coverage:**
- HACS layout, `manifest.json`, `hacs.json`, LICENSE, CI (hassfest + HACS) → Task 1.
- Channel + `(target, channel) → URL` map + OTA exceptions → Task 2.
- OTA manifest parse / app-descriptor parse / Range-fetch client with timeouts → Tasks 3, 4, 5.
- Coordinator polling per target/channel, `UpdateFailed` when all fail → Task 6.
- MQTT device tracker: parse `version` + `app`+`build-suffix` → target, dispatcher signal → Task 7.
- Config + options flow, single instance, channel selection → Task 8.
- `runtime-data`, `test-before-setup` (first refresh), `config-entry-unloading` (stop MQTT), MQTT dependency wait → Task 9.
- binary_sensor `device_class: update`, per-device, dynamic add, availability, attributes, device link, `PARALLEL_UPDATES = 0` → Task 10.
- Live e2e + lint/type/coverage gate (≥95%) → Task 11.

**Placeholder scan:** No TBD/TODO; every code step contains complete code.

**Type consistency:** `parse_manifest(data) -> str`, `parse_app_descriptor(head) -> str`, `FaikoutOtaClient(session, *, request_timeout).async_get_latest_version(manifest_url) -> str`, `manifest_url_for(target, channel) -> str | None`, `FaikoutCoordinator(hass, client, channel)` with `data: dict[str, str]`, `parse_state_payload(topic, payload, *, prefix) -> FaikoutDevice | None`, `FaikoutDeviceTracker(hass, *, prefix)` with `.devices` and `async_start`/`async_stop`, `SIGNAL_DEVICE_UPDATE` carrying a `device_id`, and `FaikoutRuntimeData(coordinator, tracker)` are used consistently across tasks and tests.
