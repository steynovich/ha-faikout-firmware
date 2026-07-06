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
