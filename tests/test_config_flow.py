"""Tests for the Faikout config flow."""

from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHANNEL: "beta"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CHANNEL: "beta"}


async def test_single_instance(hass):
    MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "stable"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_shows_form_with_current_channel_default(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "stable"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {CONF_CHANNEL: "stable"}


async def test_options_flow_updates_channel(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANNEL: "stable"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CHANNEL: "beta"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CHANNEL: "beta"}
    assert entry.options == {CONF_CHANNEL: "beta"}
