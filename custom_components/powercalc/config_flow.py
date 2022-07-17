"""Config flow for Adaptive Lighting integration."""

from __future__ import annotations
import logging
import copy
from select import select

import voluptuous as vol

from typing import Any
from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    Platform,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers import selector
from homeassistant.config_entries import ConfigEntry, OptionsFlow
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_POWER_TEMPLATE,
    CONF_CALIBRATE,
    CONF_LINEAR,
    CONF_MIN_POWER,
    CONF_MAX_POWER,
    CONF_GAMMA_CURVE,
    CONF_SENSOR_TYPE,
    CONF_ON_TIME,
    CONF_START_TIME,
    CONF_STATES_POWER,
    CONF_VALUE_TEMPLATE,
    CONF_UPDATE_FREQUENCY,
    CONF_WLED,
    DOMAIN,
    CONF_MODE,
    CONF_VALUE,
    CONF_STANDBY_POWER,
    MODE_FIXED,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_POWER,
    CONF_SUB_GROUPS,
    MODE_LINEAR,
    MODE_WLED,
    SensorType
)
from .common import SourceEntity, create_source_entity
from .sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY
from .strategy.factory import PowerCalculatorStrategyFactory
from .strategy.wled import CONFIG_SCHEMA as SCHEMA_POWER_WLED
from .strategy.strategy_interface import PowerCalculationStrategyInterface
from .errors import StrategyConfigurationError

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPE_MENU = {
    SensorType.DAILY_ENERGY: "Daily energy",
    SensorType.VIRTUAL_POWER: "Virtual power",
    SensorType.GROUP: "Group"
}

SCHEMA_DAILY_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_VALUE): selector.NumberSelector(selector.NumberSelectorConfig(min=1, mode=selector.NumberSelectorMode.BOX)),
        vol.Optional(CONF_VALUE_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME): selector.DurationSelector(selector.DurationSelectorConfig(enable_day=False)),
        #vol.Optional(CONF_START_TIME): selector.TimeSelector(),
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): selector.NumberSelector(selector.NumberSelectorConfig(min=10, unit_of_measurement="sec", mode=selector.NumberSelectorMode.BOX)),
    }
)
SCHEMA_DAILY_ENERGY = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
    }
).extend(SCHEMA_DAILY_ENERGY_OPTIONS.schema)

SCHEMA_POWER_OPTIONS = vol.Schema({
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_CREATE_ENERGY_SENSOR, default=True): selector.BooleanSelector(),
    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): selector.BooleanSelector()
})

SCHEMA_POWER = vol.Schema({
    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
    vol.Optional(CONF_NAME): selector.TextSelector(),
    vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
    vol.Optional(CONF_MODE, default=MODE_FIXED): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[MODE_FIXED, MODE_LINEAR, MODE_WLED],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    ),
}).extend(SCHEMA_POWER_OPTIONS.schema)

SCHEMA_POWER_FIXED = vol.Schema({
    vol.Optional(CONF_POWER): vol.Coerce(float),
    vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
    vol.Optional(CONF_STATES_POWER): selector.ObjectSelector()
})

SCHEMA_POWER_LINEAR = vol.Schema({
    vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
    vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
    vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
    vol.Optional(CONF_CALIBRATE): selector.ObjectSelector()
})

SCHEMA_GROUP_OPTIONS = vol.Schema({
    vol.Optional(CONF_GROUP_POWER_ENTITIES): selector.EntitySelector(
        selector.EntitySelectorConfig(domain=Platform.SENSOR, device_class=SensorDeviceClass.POWER, multiple=True)
    ),
    vol.Optional(CONF_GROUP_ENERGY_ENTITIES): selector.EntitySelector(
        selector.EntitySelectorConfig(domain=Platform.SENSOR, device_class=SensorDeviceClass.ENERGY, multiple=True)
    ),
    #vol.Required(CONF_HIDE_MEMBERS, default=False): selector.BooleanSelector(),
})

SCHEMA_GROUP = vol.Schema({
    vol.Required(CONF_NAME): str,
    vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
}).extend(SCHEMA_GROUP_OPTIONS.schema)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PowerCalc."""

    VERSION = 1

    def __init__(self):
        """Initialize options flow."""
        self.sensor_config: dict[str, Any] = dict()
        self.selected_sensor_type: str = None
        self.name: str = None
        self.source_entity: SourceEntity = None
        self.source_entity_id: str = None
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""

        return self.async_show_menu(
            step_id="user", menu_options=SENSOR_TYPE_MENU
        )

    async def async_step_virtual_power(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            self.source_entity_id = user_input[CONF_ENTITY_ID]
            self.source_entity = await create_source_entity(self.source_entity_id, self.hass)
            unique_id = user_input.get(CONF_UNIQUE_ID) or self.source_entity.unique_id or self.source_entity_id

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.name = user_input.get(CONF_NAME) or self.source_entity.name
            self.selected_sensor_type = SensorType.VIRTUAL_POWER
            self.sensor_config.update(user_input)

            if user_input.get(CONF_MODE) == MODE_FIXED:
                return await self.async_step_fixed()
            
            if user_input.get(CONF_MODE) == MODE_LINEAR:
                return await self.async_step_linear()
            
            if user_input.get(CONF_MODE) == MODE_WLED:
                return await self.async_step_wled()
            
        return self.async_show_form(
            step_id="virtual_power",
            data_schema=SCHEMA_POWER,
            errors={},
        )
    
    async def async_step_daily_energy(self, user_input: dict[str,str] = None) -> FlowResult:
        errors = _validate_daily_energy_input(user_input)

        if user_input is not None and not errors:
            unique_id = user_input.get(CONF_UNIQUE_ID) or user_input.get(CONF_NAME)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.selected_sensor_type = SensorType.DAILY_ENERGY
            self.name = user_input.get(CONF_NAME)

            self.sensor_config.update({CONF_DAILY_FIXED_ENERGY: _build_daily_energy_config(user_input)})
            return self.create_config_entry()
            
        return self.async_show_form(
            step_id="daily_energy",
            data_schema=SCHEMA_DAILY_ENERGY,
            errors=errors,
        )
    
    async def async_step_group(self, user_input: dict[str,str] = None) -> FlowResult:
        self.selected_sensor_type = SensorType.GROUP
        errors =  _validate_group_input(user_input)
        if user_input is not None:
            self.name = user_input.get(CONF_NAME)
            self.sensor_config.update(user_input)
            if not errors:
                return self.create_config_entry()

        return self.async_show_form(
            step_id="group",
            data_schema=_create_group_schema(self.hass, SCHEMA_GROUP),
            errors=errors,
        )
    
    async def async_step_fixed(self, user_input: dict[str,str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_FIXED: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return self.create_config_entry()

        return self.async_show_form(
            step_id="fixed",
            data_schema=SCHEMA_POWER_FIXED,
            errors=errors,
        )
    
    async def async_step_linear(self, user_input: dict[str,str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_LINEAR: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return self.create_config_entry()

        return self.async_show_form(
            step_id="linear",
            data_schema=_create_linear_schema(self.source_entity_id),
            errors=errors,
        )
    
    async def async_step_wled(self, user_input: dict[str,str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_WLED: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return self.create_config_entry()

        return self.async_show_form(
            step_id="wled",
            data_schema=SCHEMA_POWER_WLED,
            errors=errors,
        )
    
    async def validate_strategy_config(self) -> dict:
        strategy_name = self.sensor_config.get(CONF_MODE)
        strategy = _create_strategy_object(self.hass, strategy_name, self.sensor_config, self.source_entity)
        try:
            await strategy.validate_config()
        except StrategyConfigurationError as error:
            return {"base": error.get_config_flow_translate_key()}
        return {}
    
    @callback
    def create_config_entry(self) -> FlowResult:
        self.sensor_config.update({CONF_SENSOR_TYPE: self.selected_sensor_type})
        if self.name:
            self.sensor_config.update({CONF_NAME: self.name})
        if self.source_entity_id:
            self.sensor_config.update({CONF_ENTITY_ID: self.source_entity_id})
        if self.unique_id:
            self.sensor_config.update({CONF_UNIQUE_ID: self.unique_id})
        return self.async_create_entry(
            title=self.name, data=self.sensor_config
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle an option flow for PowerCalc."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.current_config: dict = dict(config_entry.data)
        self.sensor_type: SensorType = self.current_config.get(CONF_SENSOR_TYPE) or SensorType.VIRTUAL_POWER
        self.source_entity_id: str = self.current_config.get(CONF_ENTITY_ID)
        self.source_entity: SourceEntity = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""

        self.current_config = dict(self.config_entry.data)
        if self.source_entity_id:
            self.source_entity = await create_source_entity(self.source_entity_id, self.hass)
        
        errors = {}
        if user_input is not None:
            errors = await self.save_options(user_input)
            if not errors:
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=self.build_options_schema(),
            errors=errors,
        )

    async def save_options(self, user_input: dict[str, Any] | None = None) -> dict:
        """Save options, and return errors when validation fails"""
        if self.sensor_type == SensorType.DAILY_ENERGY:
            daily_energy_config = _build_daily_energy_config(user_input)
            self.current_config.update({CONF_DAILY_FIXED_ENERGY: daily_energy_config})
        
        if self.sensor_type == SensorType.VIRTUAL_POWER:
            self.current_config.update(
                {
                    CONF_CREATE_ENERGY_SENSOR: user_input.get(CONF_CREATE_ENERGY_SENSOR),
                    CONF_CREATE_UTILITY_METERS: user_input.get(CONF_CREATE_UTILITY_METERS),
                    CONF_STANDBY_POWER: user_input.get(CONF_STANDBY_POWER)
                }
            )
            strategy = self.current_config.get(CONF_MODE)

            strategy_options = _build_strategy_config(strategy, self.source_entity_id, user_input)
            
            self.current_config.update({strategy: strategy_options})
            strategy_object = _create_strategy_object(self.hass, strategy, self.current_config, self.source_entity)
            try:
                await strategy_object.validate_config()
            except StrategyConfigurationError as error:
                return {"base": error.get_config_flow_translate_key()}
            
        if self.sensor_type == SensorType.GROUP:
            self.current_config.update(user_input)

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=self.current_config
        )
        return {}
    
    def build_options_schema(self) -> vol.Schema:
        """Build the options schema. depending on the selected sensor type"""

        strategy_options = {}
        if self.sensor_type == SensorType.VIRTUAL_POWER:
            base_power_schema = SCHEMA_POWER_OPTIONS
            strategy: str = self.current_config.get(CONF_MODE)
            strategy_schema = _get_strategy_schema(strategy, self.source_entity_id)
            data_schema = base_power_schema.extend(strategy_schema.schema)
            strategy_options = self.current_config.get(strategy)

        if self.sensor_type == SensorType.DAILY_ENERGY:
            data_schema = SCHEMA_DAILY_ENERGY_OPTIONS
            strategy_options = self.current_config[CONF_DAILY_FIXED_ENERGY]
        
        if self.sensor_type == SensorType.GROUP:
            data_schema = _create_group_schema(self.hass, SCHEMA_GROUP_OPTIONS)
        
        data_schema = _fill_schema_defaults(data_schema, self.current_config | strategy_options)
        return data_schema
    
    def get_current_strategy_options(self, strategy: str) -> dict[str, Any]:
        strategy_options: dict[str, Any] = self.current_config.get(strategy)
        if strategy == MODE_LINEAR and CONF_CALIBRATE in strategy_options:
            calibrate_options: dict = strategy_options[CONF_CALIBRATE]
            strategy_options[CONF_CALIBRATE] = {int(key): value for (key, value) in calibrate_options.items()}
        return strategy_options

def _create_strategy_object(
    hass: HomeAssistant,
    strategy: str,
    config: dict,
    source_entity: SourceEntity
) -> PowerCalculationStrategyInterface:
    """Create the calculation strategy object"""
    factory = PowerCalculatorStrategyFactory(hass)
    return factory.create(config, strategy, None, source_entity)

def _get_strategy_schema(strategy: str, source_entity_id: str) -> vol.Schema:
    """Get the config schema for a given power calculation strategy"""
    if strategy == MODE_FIXED:
        return SCHEMA_POWER_FIXED
    if strategy == MODE_LINEAR:
        return _create_linear_schema(source_entity_id)
    if strategy == MODE_WLED:
        return SCHEMA_POWER_WLED
    return SCHEMA_POWER_FIXED

def _create_group_schema(hass: HomeAssistant, base_schema: vol.Schema) -> vol.Schema:
    """Create config schema for groups"""
    sub_groups = [
        selector.SelectOptionDict(value=config_entry.entry_id, label=config_entry.data.get(CONF_NAME))
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP
    ]

    sub_group_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(options=sub_groups, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)
    )
    return base_schema.extend(
        {
            vol.Optional(CONF_SUB_GROUPS): sub_group_selector
        }
    )

def _validate_group_input(user_input: dict[str, str] = None) -> dict:
    """Validate the group form"""
    if not user_input:
        return {}
    errors = {}

    if (not CONF_SUB_GROUPS in user_input and  
        not CONF_GROUP_POWER_ENTITIES in user_input and
        not CONF_GROUP_ENERGY_ENTITIES in user_input
    ):
        errors["base"] = "group_mandatory"
    
    return errors

def _create_linear_schema(source_entity_id: str) -> vol.Schema:
    """Create the config schema for linear strategy"""
    return SCHEMA_POWER_LINEAR.extend(
        {
            vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(selector.AttributeSelectorConfig(entity_id=source_entity_id))
        }
    )

def _build_strategy_config(strategy: str, source_entity_id: str, user_input: dict[str,str] = None) -> dict[str, Any]:
    """Build the config dict needed for the configured strategy"""
    strategy_schema = _get_strategy_schema(strategy, source_entity_id)
    strategy_options = {}
    for key in strategy_schema.schema.keys():
        if user_input.get(key) is None:
            continue
        strategy_options[str(key)] = user_input.get(key)
    return strategy_options

def _build_daily_energy_config(user_input: dict[str,str] = None) -> dict[str, Any]:
    """Build the config under daily_energy: key"""
    schema = SCHEMA_DAILY_ENERGY_OPTIONS
    config = {}
    for key in schema.schema.keys():
        if user_input.get(key) is None:
            continue
        config[str(key)] = user_input.get(key)
    return config

def _validate_daily_energy_input(user_input: dict[str, str] = None) -> dict:
    """Validates the daily energy form"""
    if not user_input:
        return {}
    errors = {}

    if not CONF_VALUE in user_input and not CONF_VALUE_TEMPLATE in user_input:
        errors["base"] = "daily_energy_mandatory"
    
    return errors

def _fill_schema_defaults(data_schema: vol.Schema, options: dict[str, str]):
    """Make a copy of the schema with suggested values set to saved options"""
    schema = {}
    for key, val in data_schema.schema.items():
        new_key = key
        if key in options:
            if isinstance(key, vol.Marker):
                if isinstance(key, vol.Optional) and callable(key.default) and key.default():
                    new_key = vol.Optional(key.schema, default=options.get(key))
                else:
                    new_key = copy.copy(key)
                    new_key.description = {"suggested_value": options.get(key)}
        schema[new_key] = val
    data_schema = vol.Schema(schema)
    return data_schema