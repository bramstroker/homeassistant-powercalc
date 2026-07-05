"""Config/options flow for a standalone cost sensor based on an existing energy sensor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
import voluptuous as vol

from custom_components.powercalc.const import (
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_SENSOR_ID,
    DOMAIN,
    DOMAIN_CONFIG,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import PowercalcFormStep, Step

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from custom_components.powercalc.config_flow import PowercalcConfigFlow, PowercalcOptionsFlow

SCHEMA_COST_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_ENERGY_SENSOR_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENERGY),
        ),
    },
)

SCHEMA_COST = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        **SCHEMA_COST_OPTIONS.schema,
    },
)


def is_global_price_configured(hass: HomeAssistant) -> bool:
    """Check whether a global energy price (fixed or sensor) has been configured."""
    global_config = hass.data.get(DOMAIN, {}).get(DOMAIN_CONFIG, {})
    return bool(global_config.get(CONF_ENERGY_PRICE) or global_config.get(CONF_ENERGY_PRICE_SENSOR))


class CostConfigFlow:
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        self.flow: PowercalcConfigFlow = flow

    async def async_step_cost(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the flow for a standalone cost sensor."""
        if not is_global_price_configured(self.flow.hass):
            return self.flow.async_abort(
                reason="cost_no_global_price",
                description_placeholders={"url": "https://docs.powercalc.nl/sensor-types/cost-sensor/"},
            )

        self.flow.selected_sensor_type = SensorType.COST
        return await self.flow.handle_form_step(
            PowercalcFormStep(step=Step.COST, schema=SCHEMA_COST),
            user_input,
        )


class CostOptionsFlow:
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_cost(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the cost sensor options flow."""
        return await self.flow.async_handle_options_step(user_input, SCHEMA_COST_OPTIONS, Step.COST)
