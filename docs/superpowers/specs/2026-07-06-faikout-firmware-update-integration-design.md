# Faikout Firmware Update — Home Assistant Integration Design

**Date:** 2026-07-06
**Status:** Approved (supersedes the earlier standalone-library design)

## Purpose

A HACS-installable Home Assistant custom integration (`faikout`) that tells you,
per Faikout device, whether a newer firmware is available on the OTA server. It
adds one **`binary_sensor` with `device_class: update`** to each existing Faikout
device: `on` = an update is available, `off` = up to date.

It only **notifies** — it does not flash firmware or command devices.

## Background — the two data sources

Faikout devices are RevK ESP32 boards already present in Home Assistant via MQTT
auto-discovery. Each device publishes a JSON state blob on `state/<hostname>`,
for example `state/faikout_zolder`:

```json
{ "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
  "build-suffix": "-S3-MINI-N4-R2", "build": "2026-07-03T08:59:45", ... }
```

From this we read, per device:

- **installed version** ← `version` (a git short-hash, e.g. `1a347969`)
- **target** ← `app` + `build-suffix` → `Faikout-S3-MINI-N4-R2`
- **identity** ← `id` (the MAC), used to link our sensor to the existing device.

The **latest available** version comes from the OTA manifest for that target and
channel. Each manifest lists a `flash` array; the entry with `"app": true` is the
application image, an ESP-IDF image whose `esp_app_desc_t` struct carries the
version. The struct is found by its magic word `0xABCD5432`; the `version` field
is a 32-byte null-padded string 16 bytes after the magic. The OTA `version` uses
the **same git-hash format** as the MQTT `version`, so comparison is exact string
equality.

Only the first 512 bytes of the app image are needed; the server sends
`Accept-Ranges: bytes`, so we fetch with an HTTP Range request (full-GET fallback).

**Channels** (user-selectable; per target):

| Channel  | Manifest URL (target `Faikout-S3-MINI-N4-R2`) |
|----------|-----------------------------------------------|
| `stable` | `https://ota.faikout.uk/Faikin-S3-MINI-N4-R2-manifest.json` |
| `beta`   | `https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json` |

Manifest URLs do not follow a derivable pattern, so `(target, channel) → URL` is a
lookup table. A device whose target is not in the table leaves its sensor
`unavailable` rather than guessing a URL.

## Architecture

```
custom_components/faikout/
├── manifest.json          # HA integration manifest (domain, mqtt dep, version)
├── const.py               # DOMAIN, Channel, MANIFEST_URLS, MQTT topic/prefix, interval
├── ota/                   # OTA fetch core — pure + async, no HA imports except aiohttp
│   ├── __init__.py
│   ├── exceptions.py      # FaikoutError, ManifestError, FirmwareParseError, FirmwareFetchError
│   ├── manifest.py        # parse_manifest(data) -> app_url
│   ├── parser.py          # parse_app_descriptor(head) -> str (version)
│   └── client.py          # FaikoutOtaClient(session).async_get_latest_version(target, channel)
├── coordinator.py         # FaikoutCoordinator(DataUpdateCoordinator): target -> latest version
├── device_tracker.py      # FaikoutDeviceTracker: subscribe MQTT, maintain id -> FaikoutDevice
├── config_flow.py         # single-instance flow; option: channel
├── __init__.py            # async_setup_entry / async_unload_entry; runtime_data
├── binary_sensor.py       # one FirmwareUpdateBinarySensor per device
├── strings.json           # + translations/en.json
```

Plus repo root: `hacs.json`, `README.md`, `LICENSE`, `.github/workflows/`, `tests/`.

### OTA core (`custom_components/faikout/ota/`)

Pure/async, no Home Assistant imports (only `aiohttp`) so it is unit-testable in
isolation and could later be extracted.

- `parse_manifest(data: bytes | str | dict) -> str` — app image URL from the
  `app: true` entry. Raises `ManifestError`.
- `parse_app_descriptor(head: bytes) -> str` — the version string. Raises
  `FirmwareParseError`.
- `class FaikoutOtaClient(session, *, request_timeout=30.0)` with
  `async def async_get_latest_version(manifest_url: str) -> str`: GET manifest →
  `parse_manifest` → Range-GET first 512 bytes of the app image (full-GET
  fallback) → `parse_app_descriptor`. Wraps `aiohttp.ClientError`, `TimeoutError`,
  and bad statuses in `FirmwareFetchError`. Never closes the injected session.

### Device tracker (`device_tracker.py`)

- Subscribes to `<prefix>+` (default prefix `state/`) via
  `homeassistant.components.mqtt.async_subscribe`.
- On each message: parse JSON; keep only payloads where `app == "Faikout"` and a
  `version` and `build-suffix` are present. Build a `FaikoutDevice`
  (`id`, `name`, `version`, `target`) keyed by `id`.
- On a new device or a changed `version`, fire a dispatcher signal so the
  binary_sensor platform can add an entity and/or entities can refresh.
- `async_stop()` unsubscribes (used by `async_unload_entry`).

### Coordinator (`coordinator.py`)

- `DataUpdateCoordinator[dict[str, str]]` mapping `target → latest_version`.
- On refresh, for each target currently seen among tracked devices, resolve the
  `(target, channel)` manifest URL and call the OTA client. Unknown targets are
  skipped. Uses HA's shared aiohttp session
  (`homeassistant.helpers.aiohttp_client.async_get_clientsession`).
- Default interval: 3 hours (`appropriate-polling`).

### binary_sensor (`binary_sensor.py`)

- One `FirmwareUpdateBinarySensor` per tracked device, added dynamically as
  devices are discovered (dispatcher-driven `async_add_entities`).
- `device_class = BinarySensorDeviceClass.UPDATE`.
- `is_on` = `device.version != coordinator.data.get(device.target)`.
- `available` = device seen **and** a latest version known for its target.
- `extra_state_attributes` = `installed_version`, `latest_version`, `channel`,
  `target`.
- `device_info` links to the existing device via the MAC connection
  (`CONNECTION_NETWORK_MAC`) so the sensor appears on the same device card.
- Subclasses `CoordinatorEntity` (for latest-version updates) and also listens to
  the tracker dispatcher signal (for installed-version updates).

### Config flow (`config_flow.py`)

- Single config entry (`unique-config-entry` / `single_instance_allowed`).
- One step: choose **channel** (`stable` default / `beta`). Channel is editable
  later via an options flow.
- MQTT is a hard dependency (`dependencies: ["mqtt"]`); the flow aborts if MQTT is
  not configured.

## Quality target — Home Assistant Silver

The integration follows the applicable Silver-tier rules (inheriting Bronze):

- **config-flow / config-flow-test-coverage / unique-config-entry:** UI setup,
  single instance, tested flow.
- **runtime-data / config-entry-unloading:** state on `entry.runtime_data`; clean
  unload unsubscribes MQTT and removes entities.
- **appropriate-polling:** 3-hour OTA poll; installed version is push (MQTT).
- **entity-unavailable / log-when-unavailable:** sensor is `unavailable` when the
  OTA fetch fails or a device hasn't reported; the coordinator logs the transition
  once (down) and once (recovered) — `FirmwareFetchError` marks the transient case.
- **test-before-setup:** `async_config_entry_first_refresh` raises
  `ConfigEntryNotReady` if the initial OTA fetch fails.
- **parallel-updates:** `PARALLEL_UPDATES = 0` (read-only sensors).
- **test-coverage:** ≥95% on the integration package.
- **code standards / dependency-transparency:** `ruff`, `mypy --strict`, a
  `manifest.json` with `version`/`codeowners`/`iot_class`, `hacs.json`, and CI
  running `hassfest` + HACS validation + the test suite.

## Testing

- **OTA core (pure):** `parse_manifest` (app-entry selection, error cases),
  `parse_app_descriptor` (crafted header, missing magic, truncation), and
  `FaikoutOtaClient` (Range happy path, full-GET fallback, timeout/error → wrapped)
  with a fake aiohttp session — no network.
- **Integration:** config flow (create entry, single-instance abort), device
  tracker (parses a real state payload, ignores non-Faikout), and binary_sensor
  `is_on`/availability, using `pytest-homeassistant-custom-component`.
- **Live e2e:** one skippable test that fetches the real stable + beta manifests
  and asserts a non-empty version.

## Non-goals (YAGNI)

- No firmware flashing / OTA triggering, no Install button.
- No deriving unknown targets' manifest URLs — only the mapped target is supported.
- No per-device channel selection (single global channel for v1).
- No config of Daikin/AC behaviour — firmware-update notification only.
