"""Config/options flow for a standalone cost sensor based on an existing energy sensor."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
import voluptuous as vol

from custom_components.powercalc.const import (
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_SENSOR_ID,
    DOMAIN,
    DOMAIN_CONFIG,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import PowercalcFormStep, Step, flatten_sections
from custom_components.powercalc.flow_helper.schema import SECTION_COST_PRICING, build_cost_pricing_schema

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcConfigFlow, PowercalcOptionsFlow


def build_cost_options_schema(hass: HomeAssistant, current_price_entity_id: str | None = None) -> vol.Schema:
    """Return the schema for the options of a standalone cost sensor."""
    return vol.Schema(
        {
            vol.Required(CONF_ENERGY_SENSOR_ID): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENERGY),
            ),
            vol.Optional(SECTION_COST_PRICING): section(
                build_cost_pricing_schema(hass, current_price_entity_id),
                {"collapsed": True},
            ),
        },
    )


def build_cost_schema(hass: HomeAssistant) -> vol.Schema:
    """Return the schema for creating a standalone cost sensor."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            **build_cost_options_schema(hass).schema,
        },
    )


def is_global_price_configured(hass: HomeAssistant) -> bool:
    """Check whether a global energy price (fixed or sensor) has been configured."""
    global_config = hass.data.get(DOMAIN, {}).get(DOMAIN_CONFIG, {})
    return bool(global_config.get(CONF_ENERGY_PRICE) or global_config.get(CONF_ENERGY_PRICE_SENSOR))


def validate_price_configured(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str] | None:
    """Ensure a price is available, either overridden on the sensor itself or globally."""
    if user_input.get(CONF_ENERGY_PRICE) or user_input.get(CONF_ENERGY_PRICE_SENSOR):
        return None
    if is_global_price_configured(hass):
        return None
    return {"base": "cost_price_mandatory"}


class CostConfigFlow:
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        self.flow: PowercalcConfigFlow = flow

    async def async_step_cost(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the flow for a standalone cost sensor."""
        self.flow.selected_sensor_type = SensorType.COST
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.COST,
                schema=build_cost_schema(self.flow.hass),
                validate_user_input=self.validate,
            ),
            user_input,
        )

    def validate(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Flatten the pricing section and reject the input when no price is available."""
        user_input = flatten_sections(user_input, build_cost_schema(self.flow.hass))
        if validate_price_configured(self.flow.hass, user_input):
            raise SchemaFlowError("cost_price_mandatory")
        return user_input


class CostOptionsFlow:
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_cost(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the cost sensor options flow."""
        return await self.flow.async_handle_options_step(
            user_input,
            build_cost_options_schema(self.flow.hass, self.flow.sensor_config.get(CONF_ENERGY_PRICE_SENSOR)),
            Step.COST,
            validate=lambda flat_input: validate_price_configured(self.flow.hass, flat_input),
        )
