"""Config and options flow for the Faikout Firmware Update integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import CONF_CHANNEL, DEFAULT_CHANNEL, DOMAIN, Channel, get_channel


def _channel_schema(default: Channel = DEFAULT_CHANNEL) -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_CHANNEL, default=default.value): vol.In([c.value for c in Channel])}
    )


class FaikoutConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    # v2 moved the channel from entry.data to entry.options.
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is None:
            # MQTT is a hard dependency: without it no device is ever discovered.
            # Checked here, on the way to the form, so it runs once per flow rather
            # than again on submit. The call can block for up to 50s while MQTT is
            # still setting up, and checking now turns the user away before they
            # have picked a channel.
            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                return self.async_abort(reason="mqtt_unavailable")
            return self.async_show_form(step_id="user", data_schema=_channel_schema())
        # The channel does not establish the connection, so it lives in options and
        # stays a single source of truth for the options flow to rewrite.
        return self.async_create_entry(title="Faikout Firmware Update", data={}, options=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FaikoutOptionsFlow()


class FaikoutOptionsFlow(OptionsFlow):
    """Allow changing the channel after setup."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        schema = _channel_schema(get_channel(self.config_entry))
        return self.async_show_form(step_id="init", data_schema=schema)
