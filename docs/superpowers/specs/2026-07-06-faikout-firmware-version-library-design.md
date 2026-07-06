# Faikout Firmware Version Library — Design

**Date:** 2026-07-06
**Status:** Approved

## Purpose

A small, reusable Python library that reports the latest available Faikout
firmware version for the `Faikout-S3-MINI-N4-R2` target, on either the **stable**
or **beta** release channel. The library is designed to be embedded later in a
Home Assistant HACS integration (e.g. an `update` entity), so it is async-first,
depends only on `aiohttp`, and injects its HTTP session rather than owning one.

A thin CLI (`faikout-version`) is provided for development and manual checks, but
the importable library is the primary interface.

## Background — how the version is discovered

The entry point is a JSON **manifest**. Each manifest lists a `flash` array of
images; the entry with `"app": true` is the application image. That image is a
standard **ESP-IDF application image** whose `esp_app_desc_t` struct carries the
version string.

The struct is located by its magic word `0xABCD5432` (little-endian on disk).
Within `esp_app_desc_t`:

| Field          | Offset (from magic) | Size | Example        |
|----------------|---------------------|------|----------------|
| `magic_word`   | 0                   | 4    | `0xABCD5432`   |
| `secure_version`| 4                  | 4    | —              |
| `reserv1`      | 8                   | 8    | —              |
| `version`      | 16                  | 32   | `1a347969`     |
| `project_name` | 48                  | 32   | `Faikout`      |
| `time`         | 80                  | 16   | `08:59:45`     |
| `date`         | 96                  | 16   | `Jul  3 2026`  |
| `idf_ver`      | 112                 | 32   | `v6.0.2`       |

All string fields are null-terminated / null-padded and decoded as ASCII/UTF-8.

In observed images the descriptor starts at file offset `0x20` and the full
256-byte struct fits within the first 512 bytes. The server sends
`Accept-Ranges: bytes`, so the client fetches only the **first 512 bytes** of the
app image via an HTTP Range request, falling back to a full GET if a server ever
ignores the Range header. This keeps periodic polling cheap (512 B vs ~1.5 MB).

## Channels

```python
class Channel(StrEnum):
    STABLE = "stable"   # default
    BETA   = "beta"
```

Each channel maps to an explicit manifest URL:

| Channel  | Manifest URL |
|----------|--------------|
| `STABLE` | `https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json` |
| `BETA`   | `https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json` |

The library never hardcodes the app image URL — it always follows the `app: true`
entry inside whichever manifest is fetched.

## Architecture

Two layers, so the reusable core has zero I/O and is trivially testable.

### 1. Pure core (synchronous, no network)

- `Channel` — `StrEnum` of `STABLE` / `BETA`.
- `manifest_url_for(channel: Channel) -> str` — resolves channel → manifest URL.
- `parse_manifest(data: bytes | str | dict) -> str` — returns the app image URL
  (the `flash` entry where `app is True`). Raises `ManifestError` if the JSON is
  malformed or no `app: true` entry with a `url` exists.
- `parse_app_descriptor(head: bytes) -> FirmwareInfo` — scans `head` for the
  magic word `0xABCD5432`, decodes the struct fields. Raises `FirmwareParseError`
  if the magic word is absent or the buffer is too short.
- `FirmwareInfo` — frozen dataclass:
  `version: str`, `project_name: str`, `idf_version: str`, `date: str`,
  `time: str`, `secure_version: int`, `app_url: str`.
- Exceptions: `FaikoutError` (base) → `ManifestError`, `FirmwareParseError`,
  `FirmwareFetchError`.

### 2. Async client (aiohttp) — what Home Assistant imports

```python
class FaikoutOtaClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        channel: Channel = Channel.STABLE,
        manifest_url: str | None = None,   # overrides channel when provided
    ) -> None: ...

    async def async_get_firmware_info(self) -> FirmwareInfo: ...
```

Flow of `async_get_firmware_info()`:

1. Resolve the manifest URL (`manifest_url` if given, else `manifest_url_for(channel)`).
2. GET the manifest → `parse_manifest` → app image URL.
3. GET the first 512 bytes of the app image with `Range: bytes=0-511`.
   If the response is not `206 Partial Content` (server ignored Range), fall back
   to a full GET and slice the first 512 bytes.
4. `parse_app_descriptor` on the bytes; attach `app_url` → return `FirmwareInfo`.

Network failures (timeouts, non-2xx/206) are wrapped in `FirmwareFetchError`. The
session is injected and never closed by the client — the caller owns its lifecycle
(Home Assistant passes its shared session; the CLI creates and closes its own).

### 3. Thin CLI

`faikout-version [--channel {stable,beta}] [--manifest-url URL]`

- Defaults to `--channel stable`.
- Creates its own `aiohttp.ClientSession`, runs the async client via
  `asyncio.run`, prints the resolved `version` to stdout.
- Exits non-zero with a concise message on any `FaikoutError`.

## Package layout

```
pyproject.toml                 # uv-managed; requires-python >=3.13; dep: aiohttp; hatchling build
src/faikout_firmware/
├── __init__.py                # public API re-exports
├── py.typed                   # PEP 561 marker
├── models.py                  # Channel, FirmwareInfo, manifest_url_for, URL constants
├── exceptions.py              # FaikoutError + subclasses
├── manifest.py                # parse_manifest
├── parser.py                  # parse_app_descriptor
├── client.py                  # FaikoutOtaClient
└── cli.py                     # faikout-version entry point
tests/
├── test_manifest.py           # app-entry selection; malformed / missing-app errors
├── test_parser.py             # version extraction from a crafted esp_app_desc_t header
└── test_e2e.py                # live fetch against the real URLs; skippable offline
```

Public API (importable by a later HACS integration):

```python
from faikout_firmware import (
    Channel, FirmwareInfo, FaikoutOtaClient,
    FaikoutError, ManifestError, FirmwareParseError, FirmwareFetchError,
)
```

## Testing

- **Unit (pure core):** `parse_manifest` selects the `app: true` entry and raises
  on malformed JSON / missing app entry; `parse_app_descriptor` extracts the
  correct fields from a hand-crafted 512-byte header and raises when the magic
  word is missing or the buffer is truncated.
- **Live e2e:** one test per channel that fetches the real manifest + app head and
  asserts a non-empty version string. Marked so it is skipped when offline / in CI
  without network (e.g. `@pytest.mark.network`, skipped on connection error).

## Non-goals (YAGNI)

- No caching, retry/backoff, or scheduling — the HA integration owns polling cadence.
- No synchronous wrapper — async-only; easy to add later if a real need appears.
- No support for other targets/chips or for flashing — version reporting only.
- No verification of bootloader / partition-table / ota_data images.
