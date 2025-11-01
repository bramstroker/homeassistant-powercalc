from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID, CONF_UNIT_OF_MEASUREMENT, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
import voluptuous as vol

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS
from custom_components.powercalc.const import (
    CONF_DAILY_FIXED_ENERGY,
    CONF_GROUP,
    CONF_ON_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import PowercalcFormStep, Step, fill_schema_defaults
from custom_components.powercalc.flow_helper.schema import SCHEMA_UTILITY_METER_TOGGLE
from custom_components.powercalc.sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcConfigFlow, PowercalcOptionsFlow

SCHEMA_DAILY_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_VALUE): vol.Coerce(float),
        vol.Optional(CONF_VALUE_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(
            CONF_UNIT_OF_MEASUREMENT,
            default=UnitOfEnergy.KILO_WATT_HOUR,
        ): vol.In(
            [UnitOfEnergy.KILO_WATT_HOUR, UnitOfPower.WATT],
        ),
        vol.Optional(CONF_ON_TIME): selector.DurationSelector(
            selector.DurationSelectorConfig(enable_day=False),
        ),
        vol.Optional(
            CONF_UPDATE_FREQUENCY,
            default=DEFAULT_DAILY_UPDATE_FREQUENCY,
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                unit_of_measurement=UnitOfTime.SECONDS,
                mode=selector.NumberSelectorMode.BOX,
            ),
        ),
    },
)
SCHEMA_DAILY_ENERGY = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
).extend(SCHEMA_DAILY_ENERGY_OPTIONS.schema)


def build_daily_energy_config(user_input: dict[str, Any], schema: vol.Schema) -> dict[str, Any]:
    """Build the config under daily_energy: key."""
    config: dict[str, Any] = {
        CONF_DAILY_FIXED_ENERGY: {},
    }
    for key, val in user_input.items():
        if key in schema.schema and val is not None:
            if key in {CONF_CREATE_UTILITY_METERS, CONF_GROUP, CONF_NAME, CONF_UNIQUE_ID}:
                config[str(key)] = val
                continue

            config[CONF_DAILY_FIXED_ENERGY][str(key)] = val
    return config


class DailyEnergyConfigFlow:
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        self.flow: PowercalcConfigFlow = flow

    async def async_step_daily_energy(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for daily energy sensor."""
        self.flow.selected_sensor_type = SensorType.DAILY_ENERGY

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            if CONF_VALUE not in user_input and CONF_VALUE_TEMPLATE not in user_input:
                raise SchemaFlowError("daily_energy_mandatory")
            return build_daily_energy_config(user_input, SCHEMA_DAILY_ENERGY)

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.DAILY_ENERGY,
                schema=SCHEMA_DAILY_ENERGY,
                validate_user_input=_validate,
                next_step=Step.ASSIGN_GROUPS,
            ),
            user_input,
        )


class DailyEnergyOptionsFlow:
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_daily_energy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the daily energy options flow."""
        schema = fill_schema_defaults(
            SCHEMA_DAILY_ENERGY_OPTIONS,
            self.flow.sensor_config[CONF_DAILY_FIXED_ENERGY],
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.DAILY_ENERGY)
