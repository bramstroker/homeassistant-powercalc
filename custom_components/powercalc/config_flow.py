"""Config flow for Adaptive Lighting integration."""

from __future__ import annotations
import logging

import voluptuous as vol

from typing import Any
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.helpers import selector
from homeassistant.config_entries import data_entry_flow, ConfigEntry, OptionsFlow
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_FIXED_RAW,
    CONF_POWER_TEMPLATE,
    CONF_CALIBRATE,
    CONF_LINEAR,
    CONF_MIN_POWER,
    CONF_MAX_POWER,
    CONF_GAMMA_CURVE,
    CONF_SENSOR_TYPE,
    CONF_ON_TIME,
    CONF_START_TIME,
    CONF_VALUE_TEMPLATE,
    CONF_UPDATE_FREQUENCY,
    CONF_WLED,
    DOMAIN,
    CONF_MODE,
    CONF_VALUE,
    CONF_STANDBY_POWER,
    CALCULATION_MODES,
    MODE_FIXED,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_POWER,
    MODE_LINEAR,
    MODE_WLED,
    SensorType
)
from .common import SourceEntity, create_source_entity
from .sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY
from .strategy.wled import CONFIG_SCHEMA as SCHEMA_POWER_WLED

_LOGGER = logging.getLogger(__name__)

SCHEMA_INITIAL = vol.Schema({
    vol.Required(CONF_SENSOR_TYPE, default=SensorType.VIRTUAL_POWER): vol.In(
        {
            SensorType.DAILY_ENERGY: "Daily energy",
            SensorType.VIRTUAL_POWER: "Virtual power",
            SensorType.GROUP: "Group"
        }
    ),
})

SCHEMA_DAILY_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_VALUE): vol.Coerce(float),
        vol.Optional(CONF_VALUE_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME): selector.DurationSelector(selector.DurationSelectorConfig(enable_day=False)),
        #vol.Optional(CONF_START_TIME): selector.TimeSelector(),
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): vol.Coerce(int),
    }
)
SCHEMA_DAILY_ENERGY = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
).extend(SCHEMA_DAILY_ENERGY_OPTIONS.schema)

SCHEMA_POWER = vol.Schema({
    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
    vol.Optional(CONF_NAME): str,
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_MODE, default=MODE_FIXED): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=CALCULATION_MODES,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    ),
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_CREATE_ENERGY_SENSOR, default=True): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): cv.boolean
})

SCHEMA_POWER_FIXED = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_FIXED_RAW): selector.ObjectSelector()
    }
)

SCHEMA_POWER_LINEAR = {
    # vol.Optional(CONF_CALIBRATE): vol.All(
    #     cv.ensure_list, [vol.Match("^[0-9]+ -> ([0-9]*[.])?[0-9]+$")]
    # ),
    vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
    vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
    vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
    vol.Optional(CONF_CALIBRATE): selector.TextSelector(selector.TextSelectorConfig(multiline=True))
}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    def __init__(self):
        """Initialize options flow."""
        self.sensor_config: dict[str, Any] = dict()
        self.name: str = None
        self.source_entity: SourceEntity = None
        self.entity_id: str = None
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""

        if not user_input:
            return self.async_show_form(
                step_id="user", data_schema=SCHEMA_INITIAL,
            )

        sensor_type = user_input[CONF_SENSOR_TYPE]
        if sensor_type == SensorType.VIRTUAL_POWER.value:
            return await self.async_step_power()

        if sensor_type == SensorType.DAILY_ENERGY.value:
            return await self.async_step_daily_energy()

        raise data_entry_flow.AbortFlow("not_implemented")

    async def async_step_power(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            self.sensor_config.update(user_input)
            self.entity_id = user_input[CONF_ENTITY_ID]
            self.source_entity = await create_source_entity(self.entity_id, self.hass)
            self.name = user_input.get(CONF_NAME) or self.source_entity.name

            unique_id = user_input.get(CONF_UNIQUE_ID) or self.source_entity.unique_id or self.entity_id
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            if user_input.get(CONF_MODE) == MODE_FIXED:
                return await self.async_step_fixed()
            
            if user_input.get(CONF_MODE) == MODE_LINEAR:
                return await self.async_step_linear()
            
            if user_input.get(CONF_MODE) == MODE_WLED:
                return await self.async_step_wled()
            
        return self.async_show_form(
            step_id="power",
            data_schema=SCHEMA_POWER,
            errors={},
        )
    
    async def async_step_daily_energy(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            unique_id = user_input.get(CONF_UNIQUE_ID) or user_input.get(CONF_NAME)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.name = user_input.get(CONF_NAME)
            sensor_config = {
                CONF_NAME: self.name,
                CONF_UNIQUE_ID: user_input.get(CONF_UNIQUE_ID),
                CONF_DAILY_FIXED_ENERGY: self.build_daily_energy_config(user_input)
            }

            self.sensor_config.update(sensor_config)
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
            )
            
        return self.async_show_form(
            step_id="daily_energy",
            data_schema=SCHEMA_DAILY_ENERGY,
            errors={},
        )

    def build_daily_energy_config(self, user_input: dict[str,str] = None) -> dict[str, Any]:
        config = {
            CONF_UPDATE_FREQUENCY: user_input[CONF_UPDATE_FREQUENCY],
            CONF_UNIT_OF_MEASUREMENT: user_input[CONF_UNIT_OF_MEASUREMENT],
            CONF_VALUE: user_input.get(CONF_VALUE) or user_input.get(CONF_VALUE_TEMPLATE)
        }
        
        if CONF_ON_TIME in user_input:
            on_time = user_input[CONF_ON_TIME]
            config[CONF_ON_TIME] = (on_time["hours"] * 3600) + (on_time["minutes"] * 60) + on_time["seconds"]
        else:
            config[CONF_ON_TIME] = 86400
        return config
    
    async def async_step_fixed(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            if CONF_FIXED_RAW in user_input:
                fixed_config = user_input[CONF_FIXED_RAW]
            else:
                power = user_input.get(CONF_POWER) or user_input.get(CONF_POWER_TEMPLATE)
                fixed_config = {CONF_POWER: power}

            self.sensor_config.update({CONF_FIXED: fixed_config})
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
            )

        return self.async_show_form(
            step_id="fixed",
            data_schema=SCHEMA_POWER_FIXED,
            errors={},
        )
    
    async def async_step_linear(self, user_input: dict[str,str] = None) -> FlowResult:
        errors = _validate_linear_input(user_input)

        if user_input is not None and not errors:
            linear_config = user_input
            self.sensor_config.update({CONF_LINEAR: linear_config})
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
            )

        config_schema = vol.Schema(
            {
                **SCHEMA_POWER_LINEAR,
                vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(selector.AttributeSelectorConfig(entity_id=self.entity_id))
            }
        )
        return self.async_show_form(
            step_id="linear",
            data_schema=config_schema,
            errors=errors,
        )
    
    async def async_step_wled(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            self.sensor_config.update({CONF_WLED: user_input})
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
            )

        return self.async_show_form(
            step_id="wled",
            data_schema=SCHEMA_POWER_WLED,
            errors={},
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle an option flow for PowerCalc."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            # save config entry here
            return

        return self.async_show_form(
            step_id="init",
            data_schema=SCHEMA_DAILY_ENERGY_OPTIONS,
            errors={},
        )

def _validate_linear_input(linear_input: dict[str, str] = None) -> dict:
    if not linear_input:
        return {}
    errors = {}

    if not CONF_MAX_POWER in linear_input and not CONF_CALIBRATE in linear_input:
        errors["base"] = "linear_mandatory"
    
    return errors