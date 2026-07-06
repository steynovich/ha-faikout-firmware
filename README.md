# Faikout Firmware Update

A Home Assistant custom integration (HACS) that adds a **firmware-update-available**
`binary_sensor` to each Faikout device. It reads each device's installed firmware
version from MQTT and compares it against the latest version published on the
Faikout OTA server for the channel you select (stable or beta). Notification only —
it does not flash firmware.

## Use cases

- Get notified in Home Assistant when any Faikout device is running outdated
  firmware, without checking each device by hand.
- Drive an automation (notification, dashboard badge, reminder) off the
  update-available state so you know when to run an OTA update on the device.

## Supported devices

Faikout (RevK) devices that publish their state over MQTT. The integration
resolves the latest firmware for known hardware targets on the OTA server. The
currently supported target is:

- `Faikout-S3-MINI-N4-R2`

Devices reporting an unrecognised target still appear, but their binary sensor
stays `unavailable` because no matching firmware manifest is published.

## Requirements

- The Home Assistant **MQTT** integration, with Faikout (RevK) devices already
  discovered (they publish `state/<hostname>` with `version` and `build-suffix`).

## Install (HACS)

Add this repository as a custom repository (category: Integration), install, then
add the **Faikout Firmware Update** integration and pick a channel.

## Configuration

The integration has a single option, set when you add it and changeable later via
the integration's **Configure** dialog:

- **Channel** — which firmware track to compare against:
  - `stable` — released firmware (default).
  - `beta` — pre-release builds.

Changing the channel reloads the integration and re-evaluates every device.

## Entities

Per device: `binary_sensor.<device>_firmware_update` — `on` when an update is
available. Attributes: `installed_version`, `latest_version`, `channel`, `target`.

## Data updates

- **Installed version** is received via MQTT push: the integration subscribes to
  `state/<hostname>` and updates a device the moment it reports.
- **Latest available version** is polled from the OTA server every **3 hours**.

A device's binary sensor turns `on` when the two versions differ.

To force an immediate re-check instead of waiting for the next poll, call Home
Assistant's built-in `homeassistant.update_entity` action against the sensor:

```yaml
action: homeassistant.update_entity
target:
  entity_id: binary_sensor.faikout_zolder_firmware_update
```

## Automation example

```yaml
automation:
  - alias: Notify when Faikout firmware update is available
    trigger:
      - platform: state
        entity_id: binary_sensor.faikout_zolder_firmware_update
        to: "on"
    action:
      - service: notify.notify
        data:
          message: >-
            Faikout update available: installed
            {{ state_attr('binary_sensor.faikout_zolder_firmware_update', 'installed_version') }},
            latest
            {{ state_attr('binary_sensor.faikout_zolder_firmware_update', 'latest_version') }}.
```

## Known limitations

- **Notification only** — it does not flash or install firmware.
- **Single instance** — only one configuration is supported.
- Only the hardware targets listed under **Supported devices** are resolved;
  other targets show as `unavailable`.
- Requires the Home Assistant **MQTT** integration and devices that publish the
  expected `state/<hostname>` payload.
- **No automatic stale-device cleanup** — a device that stops reporting over MQTT
  is not removed automatically; delete it manually (see below).

## Troubleshooting

- **Entity is `unavailable`** — the device has not reported over MQTT yet, or its
  target is not supported. Confirm the MQTT integration is connected and the
  device is publishing `state/<hostname>` with `version` and `build-suffix`.
- **No entities appear** — check that MQTT is set up and the devices are online;
  entities are created only after a device's first state message.
- **Diagnostics** — download diagnostics from the integration's device page to
  inspect the selected channel, latest versions, and tracked devices.

## Removing a device

To drop a device that no longer reports, open its device page in Home Assistant
and use **Delete**. To remove the integration entirely, delete it from
**Settings → Devices & Services**.
