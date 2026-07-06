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
