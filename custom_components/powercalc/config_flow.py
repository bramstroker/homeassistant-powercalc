"""Config flow for Adaptive Lighting integration."""
import logging

import voluptuous as vol

from typing import Any
from homeassistant import config_entries
from homeassistant.backports.enum import StrEnum
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.helpers import selector, entity_registry
from homeassistant.config_entries import data_entry_flow
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CREATE_UTILITY_METERS,
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
    CONF_UPDATE_FREQUENCY,
    DOMAIN,
    CONF_MODE,
    CONF_VALUE,
    CONF_STANDBY_POWER,
    CALCULATION_MODES,
    MODE_FIXED,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_POWER,
    MODE_LINEAR,
)
from .common import SourceEntity, create_source_entity
from .sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY

_LOGGER = logging.getLogger(__name__)

class SensorType(StrEnum):
    """Possible modes for a number selector."""

    DAILY_ENERGY = "daily_energy"
    VIRTUAL_POWER = "virtual_power"
    GROUP = "group"

SCHEMA_INITIAL = vol.Schema({
    vol.Required(CONF_SENSOR_TYPE, default=SensorType.VIRTUAL_POWER): vol.In(
        {
            SensorType.DAILY_ENERGY: "Daily energy",
            SensorType.VIRTUAL_POWER: "Virtual power",
            SensorType.GROUP: "Group"
        }
    ),
})

SCHEMA_DAILY_ENERGY = vol.Schema(
    {
        vol.Optional(CONF_VALUE): vol.Coerce(float),
        #vol.Optional(CONF_VALUE_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME): selector.DurationSelector({"enable_day": False}),
        vol.Optional(CONF_START_TIME): selector.TimeSelector(),
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): vol.Coerce(int),
    }
)

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
    vol.Optional(CONF_CREATE_UTILITY_METERS, default=True): cv.boolean
})

SCHEMA_POWER_FIXED = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_FIXED_RAW): selector.ObjectSelector()
    }
)

SCHEMA_POWER_LINEAR = {
    vol.Optional(CONF_CALIBRATE): vol.All(
        cv.ensure_list, [vol.Match("^[0-9]+ -> ([0-9]*[.])?[0-9]+$")]
    ),
    vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
    vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
    vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
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
            if CONF_NAME in user_input:
                self.name = user_input[CONF_NAME]
            else:
                self.name = self.source_entity.name

            unique_id = user_input.get(CONF_UNIQUE_ID) or self.source_entity.unique_id or self.entity_id
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            if user_input.get(CONF_MODE) == MODE_FIXED:
                return await self.async_step_fixed()
            
            if user_input.get(CONF_MODE) == MODE_LINEAR:
                return await self.async_step_linear()
            
        return self.async_show_form(
            step_id="power",
            data_schema=SCHEMA_POWER,
            errors={},
        )
    
    async def async_step_daily_energy(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            return
            
        return self.async_show_form(
            step_id="daily_energy",
            data_schema=SCHEMA_DAILY_ENERGY,
            errors={},
        )
    
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
        if user_input is not None:
            linear_config = user_input
            self.sensor_config.update({CONF_LINEAR: linear_config})
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
            )

        config_schema = vol.Schema(
            {
                **SCHEMA_POWER_LINEAR,
                vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(selector.AttributeSelectorConfig({CONF_ENTITY_ID: self.entity_id}))
            }
        )
        return self.async_show_form(
            step_id="linear",
            data_schema=config_schema,
            errors={},
        )