"""Real-power logic for the config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import voluptuous as vol

from custom_components.powercalc import SensorType
from custom_components.powercalc.flow_helper.common import PowercalcFormStep, Step, fill_schema_defaults
from custom_components.powercalc.flow_helper.schema import SCHEMA_UTILITY_METER_TOGGLE

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcConfigFlow, PowercalcOptionsFlow

SCHEMA_REAL_POWER_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(device_class=SensorDeviceClass.POWER),
        ),
        vol.Optional(CONF_DEVICE): selector.DeviceSelector(),
    },
)

SCHEMA_REAL_POWER = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        **SCHEMA_REAL_POWER_OPTIONS.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
).extend(SCHEMA_REAL_POWER_OPTIONS.schema)


class RealPowerConfigFlow:
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        self.flow: PowercalcConfigFlow = flow

    async def async_step_real_power(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for real power sensor"""

        self.flow.selected_sensor_type = SensorType.REAL_POWER
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.REAL_POWER,
                schema=SCHEMA_REAL_POWER,
                next_step=Step.ENERGY_OPTIONS,
            ),
            user_input,
        )


class RealPowerOptionsFlow:
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_real_power(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the real power options flow."""
        schema = fill_schema_defaults(
            SCHEMA_REAL_POWER_OPTIONS,
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.REAL_POWER)
