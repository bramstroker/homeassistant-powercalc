from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
import voluptuous as vol

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS
from custom_components.powercalc.const import (
    CONF_DAILY_ENERGY_VALUE,
    CONF_DAILY_FIXED_ENERGY,
    CONF_GROUP,
    CONF_ON_TIME,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import (
    PowercalcFormStep,
    Step,
    fill_schema_defaults,
    unwrap_choose_selector,
    wrap_choose_selector,
)
from custom_components.powercalc.flow_helper.schema import SCHEMA_UTILITY_METER_TOGGLE
from custom_components.powercalc.sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcConfigFlow, PowercalcOptionsFlow

DAILY_ENERGY_VALUE_CHOICES: dict[str, list[str] | str] = {
    CONF_VALUE_TEMPLATE: CONF_VALUE_TEMPLATE,
    CONF_VALUE: CONF_VALUE,
}

SCHEMA_DAILY_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_DAILY_ENERGY_VALUE): selector.ChooseSelector(
            selector.ChooseSelectorConfig(
                choices={
                    CONF_VALUE: {"selector": {"number": {"mode": "box", "step": "any"}}},
                    CONF_VALUE_TEMPLATE: {"selector": {"template": {}}},
                },
                translation_key=CONF_DAILY_ENERGY_VALUE,
            ),
        ),
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


def daily_energy_choice_key_from_validated_value(value: object) -> str:
    """Infer the daily energy config key from a validated ChooseSelector value."""
    return CONF_VALUE_TEMPLATE if isinstance(value, str) else CONF_VALUE


def build_daily_energy_config(user_input: dict[str, Any], schema: vol.Schema) -> dict[str, Any]:
    """Build the config under daily_energy: key."""
    user_input = unwrap_choose_selector(
        dict(user_input),
        CONF_DAILY_ENERGY_VALUE,
        daily_energy_choice_key_from_validated_value,
    )
    config: dict[str, Any] = {
        CONF_DAILY_FIXED_ENERGY: {},
    }
    schema_keys = {key.schema if isinstance(key, vol.Marker) else key for key in schema.schema}
    schema_keys.discard(CONF_DAILY_ENERGY_VALUE)
    schema_keys |= {CONF_VALUE, CONF_VALUE_TEMPLATE}
    for key, val in user_input.items():
        if key in schema_keys and val is not None:
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
            unwrapped = unwrap_choose_selector(
                dict(user_input),
                CONF_DAILY_ENERGY_VALUE,
                daily_energy_choice_key_from_validated_value,
            )
            if CONF_VALUE not in unwrapped and CONF_VALUE_TEMPLATE not in unwrapped:
                raise SchemaFlowError("daily_energy_mandatory")
            return build_daily_energy_config(unwrapped, SCHEMA_DAILY_ENERGY)

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
        form_data = wrap_choose_selector(
            dict(self.flow.sensor_config[CONF_DAILY_FIXED_ENERGY]),
            CONF_DAILY_ENERGY_VALUE,
            DAILY_ENERGY_VALUE_CHOICES,
        )
        schema = fill_schema_defaults(
            SCHEMA_DAILY_ENERGY_OPTIONS,
            form_data,
        )
        if user_input is not None:
            user_input = unwrap_choose_selector(
                dict(user_input),
                CONF_DAILY_ENERGY_VALUE,
                daily_energy_choice_key_from_validated_value,
            )
        return await self.flow.async_handle_options_step(user_input, schema, Step.DAILY_ENERGY)
