# Faikout Firmware Update: Home Assistant Integration Design

**Date:** 2026-07-06
**Status:** Approved (supersedes the earlier standalone-library design)

## Purpose

A HACS-installable Home Assistant custom integration (`faikout`) that tells you,
per Faikout device, whether a newer firmware is available on the OTA server. It
adds one `binary_sensor` with `device_class: update` to each existing Faikout
device: `on` = an update is available, `off` = up to date.

It only notifies you; it does not flash firmware or command devices.

## Background: the two data sources

Faikout devices are RevK ESP32 boards already present in Home Assistant via MQTT
auto-discovery. Each device publishes a JSON state blob on `state/<hostname>`,
for example `state/faikout_zolder`:

```json
{ "id": "24587CDB4CC8", "app": "Faikout", "version": "1a347969",
  "build-suffix": "-S3-MINI-N4-R2", "build": "2026-07-03T08:59:45", ... }
```

From this we read, per device:

- installed version ← `version` (a git short-hash, e.g. `1a347969`)
- target ← `app` + `build-suffix` → `Faikout-S3-MINI-N4-R2`
- identity ← `id` (the MAC), used to link our sensor to the existing device.

The latest available version comes from the OTA manifest for that target and
channel. Each manifest lists a `flash` array; the entry with `"app": true` is the
application image, an ESP-IDF image whose `esp_app_desc_t` struct carries the
version. The struct is found by its magic word `0xABCD5432`; the `version` field
is a 32-byte null-padded string 16 bytes after the magic. The OTA `version` uses
the same git-hash format as the MQTT `version`, so comparison is exact string
equality.

Only the first 512 bytes of the app image are needed. The server sends
`Accept-Ranges: bytes`, so we fetch with an HTTP Range request, and we read no
more than 512 bytes even when a server ignores the header and answers 200 with
the whole image.

Channels are user-selectable, per target:

| Channel  | Manifest URL (target `Faikout-S3-MINI-N4-R2`) |
|----------|-----------------------------------------------|
| `stable` | `https://ota.faikout.uk/Faikout.manifest` |
| `beta`   | `https://ota.faikout.uk/beta/Faikout-S3-MINI-N4-R2-beta-manifest.json` |

Manifest URLs do not follow a derivable pattern, so `(target, channel) → URL` is a
lookup table. A device whose target is not in the table leaves its sensor
`unavailable` rather than guessing a URL.

## Architecture

```
custom_components/faikout/
├── manifest.json          # HA integration manifest (domain, mqtt dep, version)
├── const.py               # DOMAIN, Channel, MANIFEST_URLS, MQTT state prefix, intervals, stale threshold
├── ota/                   # OTA fetch core — pure + async, no HA imports except aiohttp
│   ├── __init__.py
│   ├── exceptions.py      # FaikoutError, ManifestError, FirmwareParseError,
│   │                      #   FirmwareFetchError, FirmwareUnavailableError
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

- `parse_manifest(data: bytes | str | dict) -> str` returns the app image URL from
  the `app: true` entry. Raises `ManifestError`.
- `parse_app_descriptor(head: bytes) -> str` returns the version string. Raises
  `FirmwareParseError`.
- `class FaikoutOtaClient(session, *, request_timeout=30.0)` with
  `async def async_get_latest_version(manifest_url: str) -> str`: GET manifest →
  `parse_manifest` → Range-GET first 512 bytes of the app image →
  `parse_app_descriptor`. A server that ignores the Range header answers 200 with
  the whole image, so the read is bounded to 512 bytes rather than buffering it.
  Never closes the injected session.
- Fetch failures are wrapped in `FirmwareFetchError`, with
  `FirmwareUnavailableError` (a subclass) for the case where the host never
  answered: connection refused, DNS failure, or a timeout. The split matters
  because an unreachable host is an environment problem that clears on its own,
  while a bad status such as 404 is a broken URL that will not. Only the former is
  skipped by the live e2e check, and only the former is logged once per outage
  rather than on every refresh.

### Device tracker (`device_tracker.py`)

- Subscribes to `<prefix>+` (default prefix `state/`) via
  `homeassistant.components.mqtt.async_subscribe`.
- On each message: parse JSON; keep only payloads where `app == "Faikout"` and a
  `version` and `build-suffix` are present. Build a `FaikoutDevice`
  (`id`, `name`, `version`, `target`) keyed by `id`.
- Every state message records a last-seen time for its device. On a new device, a
  changed `version`, or a device coming back after being announced as gone, fire a
  dispatcher signal so the binary_sensor platform can add an entity and/or
  entities can refresh.
- MQTT has no reliable "device gone" signal, so silence is the proxy. A device is
  *stale* when unknown, or when it has published nothing for `STALE_AFTER`
  (**30 minutes**, chosen as generous for devices that report on change plus a
  periodic heartbeat, without leaving a dead device looking healthy for hours).
  `is_stale(id)` answers this; a sweep every `STALE_CHECK_INTERVAL` (1 minute)
  signals each newly stale device once, because availability is time-based and
  nothing else would trigger a state write.
- `forget(id)` drops a device and its last-seen time.
- `FaikoutDevice.is_outdated(latest)` holds the version comparison.
- `async_stop()` unsubscribes and cancels the sweep (used by `async_unload_entry`).

### Coordinator (`coordinator.py`)

- `DataUpdateCoordinator[dict[str, str]]` mapping `target → latest_version`.
- On refresh, iterate every `(target, channel)` entry in the URL table matching the
  configured channel and call the OTA client for each. Deliberately *not* driven by
  the targets currently seen among tracked devices, so `async_config_entry_first_refresh()`
  can validate OTA connectivity before any device has reported over MQTT. Uses HA's
  shared aiohttp session (`homeassistant.helpers.aiohttp_client.async_get_clientsession`).
- A refresh fails only when *no* target could be fetched. That case is left
  entirely to `DataUpdateCoordinator`, which already logs a failed refresh once on
  the way down and once on recovery; the coordinator adds nothing, so an outage is
  never reported twice.
- A *partial* failure counts as a successful refresh, so the base class says
  nothing and the missing target would otherwise be invisible. Those are logged
  here: `FirmwareUnavailableError` warns once per outage and logs a matching
  recovery, while everything else (a 404, `ManifestError`, `FirmwareParseError`)
  warns on every refresh, because the next poll will hit the same bad URL or
  bytes, and warning once and then going quiet is how a dead stable-channel
  manifest stayed hidden.
- Default interval: 3 hours (`appropriate-polling`).

### binary_sensor (`binary_sensor.py`)

- One `FirmwareUpdateBinarySensor` per tracked device, added dynamically as
  devices are discovered (dispatcher-driven `async_add_entities`).
- `device_class = BinarySensorDeviceClass.UPDATE`.
- `is_on` = `device.is_outdated(coordinator.data[device.target])`.
- `available` = the coordinator's last refresh succeeded, the device is not stale,
  *and* a latest version is known for its target. A device that stops reporting
  turns `unavailable` rather than keeping a stale "update available", and recovers
  on its next state message.
- `extra_state_attributes` = `installed_version`, `latest_version`, `channel`,
  `target`.
- `device_info` links to the existing device via the MAC connection
  (`CONNECTION_NETWORK_MAC`) so the sensor appears on the same device card, and
  supplies `identifiers`, `name`, `manufacturer` and `model` so the device is still
  fully described when this integration is the first to register it. `manufacturer`
  is the fixed string `RevK` (the firmware's author) and `model` is the build target
  (for example `Faikout-S3-MINI-N4-R2`), the only hardware identity a state message
  carries.
- Subclasses `CoordinatorEntity` (for latest-version updates) and also listens to
  the tracker dispatcher signal (for installed-version updates).

### Config flow (`config_flow.py`)

- Single config entry (`unique-config-entry` / `single_instance_allowed`).
- One step: choose the channel (`stable` default / `beta`). Channel is editable
  later via an options flow.
- MQTT is a hard dependency (`dependencies: ["mqtt"]`). The flow waits for the MQTT
  client (`mqtt.async_wait_for_mqtt_client`, up to 50 s while MQTT is still starting)
  and aborts with `mqtt_unavailable` if it never arrives. The wait happens once, on
  the way to the form, so the user is turned away before choosing a channel and the
  submit step does not block again.
- The channel default (`stable`), the options lookup (`get_channel`) and the form
  schema are each defined once and shared by the config flow, options flow and setup.

### Setup, migration and packaging

- `async_setup_entry` waits for the MQTT client the same way and raises
  `ConfigEntryNotReady` (`mqtt_unavailable`) if it is missing, so Home Assistant
  retries the entry instead of leaving it loaded with a tracker that hears nothing.
- `async_migrate_entry` refuses (returns `False`) an entry whose version is above 2:
  it was written by a newer release and this code cannot know its shape. Version 1
  entries are migrated as described under the quality target.
- `hacs.json` pins `homeassistant` to `2026.2.0`, the release the integration is
  developed and tested against.
- A manifest body that cannot be decoded is a `FirmwareFetchError`, so the
  coordinator reports it as `UpdateFailed` like any other fetch failure.

### Device removal

`async_remove_config_entry_device` refuses to remove a device that is still
reporting, since it would reappear on the next message. A stale device may be
removed; the tracker forgets it so it is not tracked again until it reports.

## Quality target: Home Assistant Gold

The integration follows the applicable Gold-tier rules (inheriting Bronze and
Silver). `custom_components/faikout/quality_scale.yaml` is the authoritative
per-rule record; `brands` remains `todo` pending an icon/logo PR against
`home-assistant/brands`, which is an external dependency rather than code work.
The manifest declares `gold`; hassfest accepts it for a custom integration while
`brands` is `todo`.

- `config-flow`, `config-flow-test-coverage`, `unique-config-entry`: UI setup,
  single instance, tested flow.
- `runtime-data`, `config-entry-unloading`: state on `entry.runtime_data`; clean
  unload unsubscribes MQTT and removes entities.
- `appropriate-polling`: 3-hour OTA poll; installed version is push (MQTT).
- `entity-unavailable`, `log-when-unavailable`: sensor is `unavailable` when the
  OTA fetch fails or a device is stale. A wholly-failed refresh is logged
  once down and once recovered by `DataUpdateCoordinator` itself; the coordinator
  only adds per-target logging for partial failures, which the base class cannot
  see (see the Coordinator section).
- `test-before-setup`: `async_config_entry_first_refresh` raises
  `ConfigEntryNotReady` if the initial OTA fetch fails.
- `parallel-updates`: `PARALLEL_UPDATES = 0` (read-only sensors).
- `test-coverage`: ≥95% on the integration package.
- Code standards and `dependency-transparency`: `ruff`, `mypy --strict`, a
  `manifest.json` with `version`/`codeowners`/`iot_class`, `hacs.json`, and CI
  running `hassfest` + HACS validation + the test suite.

Gold adds, on top of the above:

- `diagnostics`: `diagnostics.py` dumps channel, latest versions and tracked
  devices, redacting the device `id`.
- `devices`, `stale-devices`: entities carry full `device_info`, and
  `async_remove_config_entry_device` allows manual removal only of a device that has
  stopped reporting (see Device removal).
- `entity-translations`, `exception-translations`: entity names and every raised
  `ConfigEntryNotReady` / `UpdateFailed` message come from `strings.json`.
- `reconfiguration-flow` (exempt): there are no connection parameters to change;
  the channel is the only adjustable setting and the options flow handles it.

Independently of the quality scale, the channel lives in `entry.options` as the
single source of truth. Config-entry version 2 migrates v1 entries, which wrote it
to `entry.data` at creation and to `entry.options` on change, leaving every reader
to consult both.

## Testing

- OTA core (pure): `parse_manifest` (app-entry selection, error cases),
  `parse_app_descriptor` (crafted header, missing magic, truncation), and
  `FaikoutOtaClient` (Range happy path, a 200 answer that ignores the Range
  header, timeout and error wrapping) with a fake aiohttp session, no network.
- Integration: config flow (create entry, single-instance abort), device
  tracker (parses a real state payload, ignores non-Faikout; fresh, stale and
  re-appearing devices), binary_sensor `is_on`/availability (including going
  unavailable when a device is quiet and recovering), and device removal (refused
  while reporting, allowed and forgotten once quiet), using `pytest-homeassistant-custom-component`.
- Live e2e: one skippable test that fetches the real stable + beta manifests
  and asserts a non-empty version. It skips only when the host is unreachable, so
  a 404 fails the run.

## Non-goals (YAGNI)

- No firmware flashing / OTA triggering, no Install button.
- No deriving unknown targets' manifest URLs. Only the mapped target is supported.
- No per-device channel selection (single global channel for v1).
- No config of Daikin/AC behaviour; this is firmware-update notification only.
