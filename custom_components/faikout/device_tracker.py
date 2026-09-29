"""Track Faikout devices and their installed firmware version via MQTT."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import SIGNAL_DEVICE_UPDATE, STALE_AFTER, STALE_CHECK_INTERVAL, STATE_PREFIX


@dataclass(frozen=True)
class FaikoutDevice:
    id: str
    name: str
    version: str
    target: str

    def is_outdated(self, latest: str) -> bool:
        """Whether the installed version differs from ``latest``."""
        return self.version != latest


def parse_state_payload(topic: str, payload: str) -> FaikoutDevice | None:
    """Parse a Faikout MQTT state payload into a FaikoutDevice, or None."""
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("app") != "Faikout":
        return None
    dev_id = data.get("id")
    version = data.get("version")
    suffix = data.get("build-suffix")
    if not (isinstance(dev_id, str) and isinstance(version, str) and isinstance(suffix, str)):
        return None
    name = topic.removeprefix(STATE_PREFIX)
    return FaikoutDevice(id=dev_id, name=name, version=version, target=f"Faikout{suffix}")


class FaikoutDeviceTracker:
    """Subscribe to Faikout state topics and maintain a device map."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self.devices: dict[str, FaikoutDevice] = {}
        self._last_seen: dict[str, datetime] = {}
        # Devices already announced as gone, so the sweep signals each one once.
        self._announced_stale: set[str] = set()
        self._unsub: Callable[[], None] | None = None
        self._unsub_sweep: Callable[[], None] | None = None

    async def async_start(self) -> None:
        self._unsub = await mqtt.async_subscribe(
            self._hass, f"{STATE_PREFIX}+", self._handle_message, qos=0
        )
        self._unsub_sweep = async_track_time_interval(
            self._hass, self._sweep_stale, STALE_CHECK_INTERVAL
        )

    async def async_stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_sweep is not None:
            self._unsub_sweep()
            self._unsub_sweep = None

    def is_stale(self, device_id: str) -> bool:
        """Whether a device is unknown or has been silent past ``STALE_AFTER``."""
        last_seen = self._last_seen.get(device_id)
        return last_seen is None or dt_util.utcnow() - last_seen > STALE_AFTER

    def forget(self, device_id: str) -> None:
        """Drop a device so it is not tracked until it reports again."""
        self.devices.pop(device_id, None)
        self._last_seen.pop(device_id, None)
        self._announced_stale.discard(device_id)

    def track(self, device: FaikoutDevice) -> None:
        """Record a state message from ``device`` and signal if anything changed."""
        previous = self.devices.get(device.id)
        self.devices[device.id] = device
        self._last_seen[device.id] = dt_util.utcnow()
        was_stale = device.id in self._announced_stale
        self._announced_stale.discard(device.id)
        if previous != device or was_stale:
            async_dispatcher_send(self._hass, SIGNAL_DEVICE_UPDATE, device.id)

    @callback
    def _sweep_stale(self, _now: datetime) -> None:
        for device_id in self.devices:
            if device_id not in self._announced_stale and self.is_stale(device_id):
                self._announced_stale.add(device_id)
                async_dispatcher_send(self._hass, SIGNAL_DEVICE_UPDATE, device_id)

    @callback
    def _handle_message(self, msg: mqtt.ReceiveMessage) -> None:
        if not isinstance(msg.payload, str):
            return
        device = parse_state_payload(msg.topic, msg.payload)
        if device is None:
            return
        self.track(device)
