"""Tests for the Faikout config flow."""

from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.faikout.const import CONF_CHANNEL, DOMAIN


async def test_user_flow_creates_entry(hass, mqtt_mock):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHANNEL: "beta"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    # The channel is not needed to establish the connection, so it belongs in
    # options, where the options flow can rewrite it without a second source.
    assert result["options"] == {CONF_CHANNEL: "beta"}
    assert result["data"] == {}


async def test_user_flow_aborts_when_mqtt_not_configured(hass):
    with patch(
        "custom_components.faikout.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "mqtt_unavailable"


async def test_mqtt_is_checked_once_per_flow_not_on_every_step(hass, mqtt_mock):
    # async_wait_for_mqtt_client blocks for up to 50s while MQTT is still setting
    # up, so the flow must not call it again when the user submits the form.
    with (
        patch(
            "custom_components.faikout.config_flow.mqtt.async_wait_for_mqtt_client",
            return_value=True,
        ) as wait,
        # Entry setup runs the same check for its own reasons; stub it out so this
        # test counts only what the flow itself does.
        patch("custom_components.faikout.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert wait.call_count == 1
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CHANNEL: "beta"})

    assert wait.call_count == 1


async def test_single_instance(hass):
    MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "stable"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_shows_form_with_current_channel_default(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "stable"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {CONF_CHANNEL: "stable"}


async def test_options_flow_updates_channel(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={CONF_CHANNEL: "stable"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CHANNEL: "beta"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CHANNEL: "beta"}
    assert entry.options == {CONF_CHANNEL: "beta"}
