# Faikout Firmware Version Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a uv-managed Python library that reports the latest Faikout `Faikout-S3-MINI-N4-R2` firmware version on the stable or beta channel, designed for later embedding in a Home Assistant HACS integration.

**Architecture:** A pure, I/O-free core (channel resolution, manifest JSON parsing, ESP-IDF `esp_app_desc_t` parsing) sits beneath an async `aiohttp` client that injects its session. A thin CLI wraps the async client via `asyncio.run`. The client fetches only the first 512 bytes of the app image using an HTTP Range request.

**Tech Stack:** Python >=3.13, uv, aiohttp, hatchling, pytest, pytest-asyncio.

## Global Constraints

- `requires-python = ">=3.13"` — do not pin to a single version.
- Only runtime dependency is `aiohttp`. No `httpx`, `requests`, or other HTTP libs.
- `src/` layout under `src/faikout_firmware/`; ship a `py.typed` marker (PEP 561).
- Build backend: `hatchling`.
- Async-only public API. No synchronous wrapper.
- Never hardcode the app image `.bin` URL — always follow the manifest's `app: true` entry.
- Stable manifest: `https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json`
- Beta manifest: `https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json`
- ESP-IDF app descriptor magic word: `0xABCD5432` (little-endian on disk). `version` field is a 32-byte null-padded string at offset +16 from the magic word.

---

### Task 1: Project scaffolding (uv, pyproject, package skeleton)

**Files:**
- Create: `pyproject.toml`
- Create: `src/faikout_firmware/__init__.py`
- Create: `src/faikout_firmware/py.typed` (empty)
- Create: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: an installed, importable `faikout_firmware` package; `uv run` and `pytest` work.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "faikout-firmware"
version = "0.1.0"
description = "Report the latest Faikout firmware version from the OTA manifest (stable/beta)."
readme = "README.md"
requires-python = ">=3.13"
dependencies = ["aiohttp>=3.9"]

[project.scripts]
faikout-version = "faikout_firmware.cli:main"

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/faikout_firmware"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["network: tests that hit the live OTA server (skipped when offline)"]
```

- [ ] **Step 2: Create package skeleton files**

`src/faikout_firmware/py.typed` — empty file.

`README.md`:

```markdown
# faikout-firmware

Report the latest Faikout `Faikout-S3-MINI-N4-R2` firmware version from the OTA
manifest, on the stable or beta channel. Async, `aiohttp`-based, and designed to
be embedded in a Home Assistant integration.

## CLI

    uv run faikout-version --channel beta
```

`src/faikout_firmware/__init__.py` (placeholder re-exports, expanded in Task 6):

```python
"""Report the latest Faikout firmware version from the OTA manifest."""

__all__: list[str] = []
```

- [ ] **Step 3: Pin Python and sync the environment**

Run: `uv python pin 3.13 && uv sync`
Expected: creates `.venv`, resolves `aiohttp` + dev group, writes `uv.lock`. No errors.

- [ ] **Step 4: Verify the package imports**

Run: `uv run python -c "import faikout_firmware; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .python-version README.md src/faikout_firmware/__init__.py src/faikout_firmware/py.typed
git commit -m "chore: scaffold uv project skeleton"
```

---

### Task 2: Exceptions and models (Channel, FirmwareInfo, URL resolution)

**Files:**
- Create: `src/faikout_firmware/exceptions.py`
- Create: `src/faikout_firmware/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class FaikoutError(Exception)`; subclasses `ManifestError`, `FirmwareParseError`, `FirmwareFetchError` (all extend `FaikoutError`).
  - `class Channel(StrEnum)` with members `STABLE = "stable"`, `BETA = "beta"`.
  - `manifest_url_for(channel: Channel) -> str`.
  - `@dataclass(frozen=True, slots=True) class FirmwareInfo` with fields `version: str`, `project_name: str`, `idf_version: str`, `date: str`, `time: str`, `secure_version: int`, `app_url: str`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
import pytest

from faikout_firmware.exceptions import (
    FaikoutError, ManifestError, FirmwareParseError, FirmwareFetchError,
)
from faikout_firmware.models import Channel, FirmwareInfo, manifest_url_for


def test_channel_values():
    assert Channel.STABLE == "stable"
    assert Channel.BETA == "beta"
    assert Channel("beta") is Channel.BETA


def test_manifest_url_for_each_channel():
    assert manifest_url_for(Channel.STABLE) == (
        "https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json"
    )
    assert manifest_url_for(Channel.BETA) == (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    )


def test_exception_hierarchy():
    for exc in (ManifestError, FirmwareParseError, FirmwareFetchError):
        assert issubclass(exc, FaikoutError)


def test_firmware_info_is_frozen():
    info = FirmwareInfo(
        version="1a347969", project_name="Faikout", idf_version="v6.0.2",
        date="Jul  3 2026", time="08:59:45", secure_version=0,
        app_url="https://example/app.bin",
    )
    assert info.version == "1a347969"
    with pytest.raises(Exception):
        info.version = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'faikout_firmware.exceptions'`.

- [ ] **Step 3: Write `exceptions.py`**

```python
"""Exception hierarchy for the faikout_firmware library."""


class FaikoutError(Exception):
    """Base class for all faikout_firmware errors."""


class ManifestError(FaikoutError):
    """The OTA manifest was missing, malformed, or had no app entry."""


class FirmwareParseError(FaikoutError):
    """The firmware image did not contain a valid ESP-IDF app descriptor."""


class FirmwareFetchError(FaikoutError):
    """A network request to the OTA server failed."""
```

- [ ] **Step 4: Write `models.py`**

```python
"""Channels, URL resolution, and the FirmwareInfo result type."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Channel(StrEnum):
    STABLE = "stable"
    BETA = "beta"


_MANIFEST_URLS: dict[Channel, str] = {
    Channel.STABLE: "https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json",
    Channel.BETA: "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json",
}


def manifest_url_for(channel: Channel) -> str:
    """Return the manifest URL for the given release channel."""
    return _MANIFEST_URLS[channel]


@dataclass(frozen=True, slots=True)
class FirmwareInfo:
    version: str
    project_name: str
    idf_version: str
    date: str
    time: str
    secure_version: int
    app_url: str
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/faikout_firmware/exceptions.py src/faikout_firmware/models.py tests/test_models.py
git commit -m "feat: add exceptions, Channel, and FirmwareInfo model"
```

---

### Task 3: Manifest parser

**Files:**
- Create: `src/faikout_firmware/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `ManifestError` from `faikout_firmware.exceptions`.
- Produces: `parse_manifest(data: bytes | str | dict) -> str` — returns the URL of the `flash` entry whose `app` value is `True`. Raises `ManifestError` on invalid JSON, non-object payloads, a missing/empty `flash` list, no `app: true` entry, or an app entry lacking a `url`.

- [ ] **Step 1: Write the failing test**

`tests/test_manifest.py`:

```python
import json

import pytest

from faikout_firmware.exceptions import ManifestError
from faikout_firmware.manifest import parse_manifest

VALID = {
    "flash": [
        {"url": "https://ota.faikout.uk/Faikout-S3-MINI-N4-R2-bootloader.bin"},
        {"address": "8000", "url": "https://ota.faikout.uk/part.bin"},
        {"address": "10000", "url": "https://ota.faikout.uk/app.bin", "app": True},
    ]
}


def test_returns_app_url_from_dict():
    assert parse_manifest(VALID) == "https://ota.faikout.uk/app.bin"


def test_returns_app_url_from_bytes():
    assert parse_manifest(json.dumps(VALID).encode()) == "https://ota.faikout.uk/app.bin"


def test_returns_app_url_from_str():
    assert parse_manifest(json.dumps(VALID)) == "https://ota.faikout.uk/app.bin"


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

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'faikout_firmware.manifest'`.

- [ ] **Step 3: Write `manifest.py`**

```python
"""Parse an OTA manifest and return the application image URL."""

from __future__ import annotations

import json
from typing import Any

from .exceptions import ManifestError


def parse_manifest(data: bytes | str | dict[str, Any]) -> str:
    """Return the URL of the ``flash`` entry with ``app: true``.

    Raises ManifestError if the payload is not a JSON object, has no ``flash``
    list, has no ``app: true`` entry, or that entry lacks a ``url``.
    """
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

Run: `uv run pytest tests/test_manifest.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/faikout_firmware/manifest.py tests/test_manifest.py
git commit -m "feat: parse OTA manifest to app image URL"
```

---

### Task 4: ESP-IDF app descriptor parser

**Files:**
- Create: `src/faikout_firmware/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `FirmwareParseError` from `faikout_firmware.exceptions`; `FirmwareInfo` from `faikout_firmware.models`.
- Produces: `parse_app_descriptor(head: bytes, *, app_url: str = "") -> FirmwareInfo`. Locates the magic word `0xABCD5432` (little-endian bytes `52 54 CD AB`) in `head`, decodes the `esp_app_desc_t` struct that starts there, and returns a `FirmwareInfo` (with `app_url` passed through). Raises `FirmwareParseError` if the magic word is absent or the buffer is truncated before the end of the struct.

**Struct layout (offsets from the magic word):** magic `u32` @0; `secure_version` `u32` @4; reserved 8 bytes @8; `version` `char[32]` @16; `project_name` `char[32]` @48; `time` `char[16]` @80; `date` `char[16]` @96; `idf_ver` `char[32]` @112. Bytes needed from the magic word: 144.

- [ ] **Step 1: Write the failing test**

`tests/test_parser.py`:

```python
import struct

import pytest

from faikout_firmware.exceptions import FirmwareParseError
from faikout_firmware.parser import parse_app_descriptor

MAGIC = 0xABCD5432


def _field(text: str, size: int) -> bytes:
    raw = text.encode("ascii")
    return raw + b"\x00" * (size - len(raw))


def _descriptor(
    version="1a347969", project="Faikout", time="08:59:45",
    date="Jul  3 2026", idf="v6.0.2", secure_version=0,
) -> bytes:
    body = struct.pack("<II", MAGIC, secure_version) + b"\x00" * 8
    body += _field(version, 32)
    body += _field(project, 32)
    body += _field(time, 16)
    body += _field(date, 16)
    body += _field(idf, 32)
    return body


def test_parses_descriptor_at_offset_zero():
    info = parse_app_descriptor(_descriptor(), app_url="https://x/app.bin")
    assert info.version == "1a347969"
    assert info.project_name == "Faikout"
    assert info.idf_version == "v6.0.2"
    assert info.date == "Jul  3 2026"
    assert info.time == "08:59:45"
    assert info.secure_version == 0
    assert info.app_url == "https://x/app.bin"


def test_finds_descriptor_after_image_header():
    # Real images place the descriptor 32 bytes in, behind the image header.
    head = b"\xe9\x07\x02\x20" + b"\x11" * 28 + _descriptor()
    info = parse_app_descriptor(head)
    assert info.version == "1a347969"


def test_missing_magic_raises():
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(b"\x00" * 512)


def test_truncated_after_magic_raises():
    truncated = _descriptor()[:100]  # magic present, struct incomplete
    with pytest.raises(FirmwareParseError):
        parse_app_descriptor(truncated)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'faikout_firmware.parser'`.

- [ ] **Step 3: Write `parser.py`**

```python
"""Parse an ESP-IDF esp_app_desc_t struct out of a firmware image head."""

from __future__ import annotations

import struct

from .exceptions import FirmwareParseError
from .models import FirmwareInfo

_MAGIC = 0xABCD5432
_MAGIC_BYTES = struct.pack("<I", _MAGIC)  # b"\x52\x54\xcd\xab"

# Offsets from the magic word within esp_app_desc_t.
_SECURE_VERSION_OFF = 4
_VERSION_OFF = 16
_PROJECT_OFF = 48
_TIME_OFF = 80
_DATE_OFF = 96
_IDF_OFF = 112
_STRUCT_MIN_LEN = 144  # through the end of idf_ver[32]


def _cstr(buf: bytes, start: int, size: int) -> str:
    raw = buf[start : start + size]
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def parse_app_descriptor(head: bytes, *, app_url: str = "") -> FirmwareInfo:
    """Locate esp_app_desc_t via its magic word and decode it."""
    base = head.find(_MAGIC_BYTES)
    if base == -1:
        raise FirmwareParseError("app descriptor magic word 0xABCD5432 not found")
    if len(head) - base < _STRUCT_MIN_LEN:
        raise FirmwareParseError("firmware head truncated before end of app descriptor")

    (secure_version,) = struct.unpack_from("<I", head, base + _SECURE_VERSION_OFF)
    return FirmwareInfo(
        version=_cstr(head, base + _VERSION_OFF, 32),
        project_name=_cstr(head, base + _PROJECT_OFF, 32),
        time=_cstr(head, base + _TIME_OFF, 16),
        date=_cstr(head, base + _DATE_OFF, 16),
        idf_version=_cstr(head, base + _IDF_OFF, 32),
        secure_version=secure_version,
        app_url=app_url,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parser.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/faikout_firmware/parser.py tests/test_parser.py
git commit -m "feat: parse ESP-IDF app descriptor for version fields"
```

---

### Task 5: Async aiohttp client

**Files:**
- Create: `src/faikout_firmware/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `parse_manifest`, `parse_app_descriptor`, `Channel`, `manifest_url_for`, `FirmwareInfo`, and `FirmwareFetchError`.
- Produces:
  - `class FaikoutOtaClient` with `__init__(self, session: aiohttp.ClientSession, *, channel: Channel = Channel.STABLE, manifest_url: str | None = None)` and `async def async_get_firmware_info(self) -> FirmwareInfo`.
  - Module constant `HEAD_BYTES = 512`.
  - Flow: resolve manifest URL (explicit `manifest_url` wins over `channel`) → GET manifest text → `parse_manifest` → GET app image with `Range: bytes=0-511`; if the response status is not `206`, re-GET the whole body and slice `[:HEAD_BYTES]` → `parse_app_descriptor(head, app_url=...)`. Wrap `aiohttp.ClientError` and non-2xx/206 statuses in `FirmwareFetchError`. Never close the injected session.

- [ ] **Step 1: Write the failing test**

`tests/test_client.py` (uses a fake session — no real network):

```python
import struct

import pytest

from faikout_firmware.client import FaikoutOtaClient, HEAD_BYTES
from faikout_firmware.exceptions import FirmwareFetchError
from faikout_firmware.models import Channel

MAGIC = 0xABCD5432


def _field(text, size):
    return text.encode("ascii").ljust(size, b"\x00")


def _app_head():
    body = struct.pack("<II", MAGIC, 0) + b"\x00" * 8
    body += _field("1a347969", 32) + _field("Faikout", 32)
    body += _field("08:59:45", 16) + _field("Jul  3 2026", 16) + _field("v6.0.2", 32)
    return body.ljust(HEAD_BYTES, b"\x00")


MANIFEST = b'{"flash":[{"url":"https://x/app.bin","app":true}]}'


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
            import aiohttp
            raise aiohttp.ClientError(f"status {self.status}")


class FakeSession:
    """Returns queued responses; records requested URLs and headers."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, headers=None):
        self.calls.append((url, headers))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_happy_path_uses_range_request():
    session = FakeSession([
        FakeResponse(200, MANIFEST),
        FakeResponse(206, _app_head()),
    ])
    client = FaikoutOtaClient(session, channel=Channel.BETA)
    info = await client.async_get_firmware_info()

    assert info.version == "1a347969"
    assert info.app_url == "https://x/app.bin"
    # manifest URL is the beta one; app request carried a Range header.
    assert session.calls[0][0] == (
        "https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json"
    )
    assert session.calls[1][0] == "https://x/app.bin"
    assert session.calls[1][1]["Range"] == "bytes=0-511"
    assert session.closed is False  # client must not close injected session


@pytest.mark.asyncio
async def test_full_get_fallback_when_range_ignored():
    full_body = b"\x00" * 32 + _app_head()  # server ignored Range, sent 200 + full body
    session = FakeSession([
        FakeResponse(200, MANIFEST),
        FakeResponse(200, full_body),
    ])
    client = FaikoutOtaClient(session)
    info = await client.async_get_firmware_info()
    assert info.version == "1a347969"


@pytest.mark.asyncio
async def test_explicit_manifest_url_overrides_channel():
    session = FakeSession([
        FakeResponse(200, MANIFEST),
        FakeResponse(206, _app_head()),
    ])
    client = FaikoutOtaClient(
        session, channel=Channel.STABLE, manifest_url="https://custom/m.json"
    )
    await client.async_get_firmware_info()
    assert session.calls[0][0] == "https://custom/m.json"


@pytest.mark.asyncio
async def test_network_error_wrapped():
    import aiohttp

    class BoomSession:
        def get(self, url, headers=None):
            raise aiohttp.ClientError("boom")

    client = FaikoutOtaClient(BoomSession())
    with pytest.raises(FirmwareFetchError):
        await client.async_get_firmware_info()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'faikout_firmware.client'`.

- [ ] **Step 3: Write `client.py`**

```python
"""Async aiohttp client that resolves the latest firmware version."""

from __future__ import annotations

import aiohttp

from .exceptions import FirmwareFetchError
from .manifest import parse_manifest
from .models import Channel, FirmwareInfo, manifest_url_for
from .parser import parse_app_descriptor

HEAD_BYTES = 512


class FaikoutOtaClient:
    """Fetch and parse the latest Faikout firmware version for a channel.

    The aiohttp session is injected and never closed by this client — the
    caller owns its lifecycle (Home Assistant passes its shared session).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        channel: Channel = Channel.STABLE,
        manifest_url: str | None = None,
    ) -> None:
        self._session = session
        self._manifest_url = manifest_url or manifest_url_for(channel)

    async def async_get_firmware_info(self) -> FirmwareInfo:
        manifest_text = await self._get_text(self._manifest_url)
        app_url = parse_manifest(manifest_text)
        head = await self._get_head(app_url)
        return parse_app_descriptor(head, app_url=app_url)

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(url) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err

    async def _get_head(self, url: str) -> bytes:
        headers = {"Range": f"bytes=0-{HEAD_BYTES - 1}"}
        try:
            async with self._session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                body = await resp.read()
                if resp.status == 206:
                    return body
                # Server ignored Range and sent the full body; slice the head.
                return body[:HEAD_BYTES]
        except aiohttp.ClientError as err:
            raise FirmwareFetchError(f"failed to fetch {url}: {err}") from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/faikout_firmware/client.py tests/test_client.py
git commit -m "feat: add async aiohttp OTA client with Range fetch"
```

---

### Task 6: Public API exports

**Files:**
- Modify: `src/faikout_firmware/__init__.py`
- Test: `tests/test_public_api.py`

**Interfaces:**
- Consumes: everything from Tasks 2–5.
- Produces: top-level importable names `Channel`, `FirmwareInfo`, `FaikoutOtaClient`, `manifest_url_for`, `parse_manifest`, `parse_app_descriptor`, `FaikoutError`, `ManifestError`, `FirmwareParseError`, `FirmwareFetchError`, all listed in `__all__`.

- [ ] **Step 1: Write the failing test**

`tests/test_public_api.py`:

```python
import faikout_firmware as ff


def test_public_names_importable():
    for name in (
        "Channel", "FirmwareInfo", "FaikoutOtaClient", "manifest_url_for",
        "parse_manifest", "parse_app_descriptor",
        "FaikoutError", "ManifestError", "FirmwareParseError", "FirmwareFetchError",
    ):
        assert hasattr(ff, name), name
        assert name in ff.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — `AssertionError: Channel` (name not exported yet).

- [ ] **Step 3: Rewrite `__init__.py`**

```python
"""Report the latest Faikout firmware version from the OTA manifest."""

from .client import FaikoutOtaClient
from .exceptions import (
    FaikoutError,
    FirmwareFetchError,
    FirmwareParseError,
    ManifestError,
)
from .manifest import parse_manifest
from .models import Channel, FirmwareInfo, manifest_url_for
from .parser import parse_app_descriptor

__all__ = [
    "Channel",
    "FirmwareInfo",
    "FaikoutOtaClient",
    "manifest_url_for",
    "parse_manifest",
    "parse_app_descriptor",
    "FaikoutError",
    "ManifestError",
    "FirmwareParseError",
    "FirmwareFetchError",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/faikout_firmware/__init__.py tests/test_public_api.py
git commit -m "feat: expose public API from package root"
```

---

### Task 7: CLI

**Files:**
- Create: `src/faikout_firmware/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Channel`, `FaikoutOtaClient`, `FaikoutError`.
- Produces:
  - `def main(argv: list[str] | None = None) -> int` — the `faikout-version` console entry point registered in Task 1.
  - `async def _run(channel: Channel, manifest_url: str | None) -> str` — builds an `aiohttp.ClientSession`, calls the client, returns the version string; the session is closed in a `finally`/`async with`.
  - Args: `--channel {stable,beta}` (default `stable`), `--manifest-url URL` (optional). On success prints the version and returns `0`; on any `FaikoutError` prints `error: <msg>` to stderr and returns `1`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
import faikout_firmware.cli as cli
from faikout_firmware.exceptions import FirmwareFetchError


def test_main_prints_version(monkeypatch, capsys):
    async def fake_run(channel, manifest_url):
        assert channel.value == "beta"
        return "1a347969"

    monkeypatch.setattr(cli, "_run", fake_run)
    rc = cli.main(["--channel", "beta"])
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.strip() == "1a347969"


def test_main_defaults_to_stable(monkeypatch, capsys):
    seen = {}

    async def fake_run(channel, manifest_url):
        seen["channel"] = channel.value
        return "v1"

    monkeypatch.setattr(cli, "_run", fake_run)
    cli.main([])
    assert seen["channel"] == "stable"


def test_main_handles_error(monkeypatch, capsys):
    async def fake_run(channel, manifest_url):
        raise FirmwareFetchError("network down")

    monkeypatch.setattr(cli, "_run", fake_run)
    rc = cli.main([])
    err = capsys.readouterr().err
    assert rc == 1
    assert "network down" in err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'faikout_firmware.cli'`.

- [ ] **Step 3: Write `cli.py`**

```python
"""Command-line entry point: print the latest firmware version."""

from __future__ import annotations

import argparse
import asyncio
import sys

import aiohttp

from .client import FaikoutOtaClient
from .exceptions import FaikoutError
from .models import Channel


async def _run(channel: Channel, manifest_url: str | None) -> str:
    async with aiohttp.ClientSession() as session:
        client = FaikoutOtaClient(session, channel=channel, manifest_url=manifest_url)
        info = await client.async_get_firmware_info()
        return info.version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faikout-version",
        description="Print the latest Faikout firmware version.",
    )
    parser.add_argument(
        "--channel",
        type=Channel,
        choices=list(Channel),
        default=Channel.STABLE,
        help="release channel (default: stable)",
    )
    parser.add_argument(
        "--manifest-url",
        default=None,
        help="override the manifest URL (ignores --channel)",
    )
    args = parser.parse_args(argv)

    try:
        version = asyncio.run(_run(args.channel, args.manifest_url))
    except FaikoutError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/faikout_firmware/cli.py tests/test_cli.py
git commit -m "feat: add faikout-version CLI"
```

---

### Task 8: Live end-to-end test (skippable offline)

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Consumes: `FaikoutOtaClient`, `Channel`.
- Produces: one parametrized network test per channel that skips cleanly when the server is unreachable.

- [ ] **Step 1: Write the test**

`tests/test_e2e.py`:

```python
import aiohttp
import pytest

from faikout_firmware import Channel, FaikoutOtaClient


@pytest.mark.network
@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [Channel.STABLE, Channel.BETA])
async def test_live_version_is_nonempty(channel):
    try:
        async with aiohttp.ClientSession() as session:
            client = FaikoutOtaClient(session, channel=channel)
            info = await client.async_get_firmware_info()
    except aiohttp.ClientError as err:
        pytest.skip(f"OTA server unreachable: {err}")

    assert info.version
    assert info.app_url.endswith(".bin")
    assert info.project_name  # e.g. "Faikout"
```

- [ ] **Step 2: Run the full suite excluding network, confirm it passes**

Run: `uv run pytest -m "not network" -v`
Expected: PASS — all unit tests across Tasks 2–7 pass; the network test is deselected.

- [ ] **Step 3: Run the live test (requires network)**

Run: `uv run pytest -m network -v`
Expected: PASS for both channels (or SKIP if offline). Prints no errors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add skippable live e2e version check"
```

---

## Self-Review

**Spec coverage:**
- Purpose / library-first, async, aiohttp-only, injected session → Tasks 1, 5.
- Version discovery via manifest → app `.bin` → esp_app_desc_t → Tasks 3, 4, 5.
- Magic-word `0xABCD5432`, version at +16 → Task 4.
- 512-byte Range fetch with full-GET fallback → Task 5 (`_get_head`, `HEAD_BYTES`).
- Channels (STABLE default / BETA) + explicit URLs + `manifest_url` override → Tasks 2, 5.
- Pure core with no I/O → Tasks 2, 3, 4 (no aiohttp import).
- `FirmwareInfo` fields → Task 2, populated in Task 4.
- Typed exception hierarchy → Task 2, used in Tasks 3–5, 7.
- Thin CLI with `--channel` / `--manifest-url` via `asyncio.run` → Task 7.
- Public API re-exports → Task 6.
- Unit tests on pure core + skippable live e2e → Tasks 2–8.
- Constraints: `>=3.13`, aiohttp-only, `src/` layout, `py.typed`, hatchling → Task 1.

**Placeholder scan:** No TBD/TODO; every code step contains complete code.

**Type consistency:** `parse_manifest(data) -> str`, `parse_app_descriptor(head, *, app_url="") -> FirmwareInfo`, `manifest_url_for(channel) -> str`, `FaikoutOtaClient(session, *, channel, manifest_url).async_get_firmware_info() -> FirmwareInfo`, `HEAD_BYTES = 512`, and `_run(channel, manifest_url)` are used consistently across tasks and tests.
