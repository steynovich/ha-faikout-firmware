"""Track Faikout devices and their installed firmware version via MQTT."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
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
        self._unsub: Callable[[], None] | None = None

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
        if not isinstance(msg.payload, str):
            return
        device = parse_state_payload(msg.topic, msg.payload, prefix=self._prefix)
        if device is None:
            return
        previous = self.devices.get(device.id)
        self.devices[device.id] = device
        if previous != device:
            async_dispatcher_send(self._hass, SIGNAL_DEVICE_UPDATE, device.id)
