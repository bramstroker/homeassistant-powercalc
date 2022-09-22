"""Config flow for Adaptive Lighting integration."""

from __future__ import annotations

import copy
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, OptionsFlow
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_GAMMA_CURVE,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_ON_TIME,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_SUB_GROUPS,
    CONF_SUB_PROFILE,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    CONF_WLED,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)
from .errors import ModelNotSupported, StrategyConfigurationError
from .power_profile.library import ModelInfo, ProfileLibrary
from .power_profile.model_discovery import get_power_profile
from .sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY
from .strategy.factory import PowerCalculatorStrategyFactory
from .strategy.strategy_interface import PowerCalculationStrategyInterface
from .strategy.wled import CONFIG_SCHEMA as SCHEMA_POWER_WLED

_LOGGER = logging.getLogger(__name__)

CONF_CONFIRM_AUTODISCOVERED_MODEL = "confirm_autodisovered_model"

SENSOR_TYPE_MENU = {
    SensorType.DAILY_ENERGY: "Daily energy",
    SensorType.VIRTUAL_POWER: "Virtual power",
    SensorType.GROUP: "Group",
}

SCHEMA_DAILY_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_VALUE): vol.Coerce(float),
        vol.Optional(CONF_VALUE_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=ENERGY_KILO_WATT_HOUR): vol.In(
            [ENERGY_KILO_WATT_HOUR, POWER_WATT]
        ),
        vol.Optional(CONF_ON_TIME): selector.DurationSelector(
            selector.DurationSelectorConfig(enable_day=False)
        ),
        # vol.Optional(CONF_START_TIME): selector.TimeSelector(),
        vol.Optional(
            CONF_UPDATE_FREQUENCY, default=DEFAULT_DAILY_UPDATE_FREQUENCY
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10, unit_of_measurement="sec", mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
)
SCHEMA_DAILY_ENERGY = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
    }
).extend(SCHEMA_DAILY_ENERGY_OPTIONS.schema)

SCHEMA_POWER_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
        vol.Optional(
            CONF_CREATE_ENERGY_SENSOR, default=True
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_CREATE_UTILITY_METERS, default=False
        ): selector.BooleanSelector(),
    }
)

SCHEMA_POWER_BASE = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
        vol.Optional(CONF_NAME): selector.TextSelector(),
        vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
        vol.Optional(
            CONF_MODE, default=CalculationStrategy.FIXED
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    CalculationStrategy.FIXED,
                    CalculationStrategy.LINEAR,
                    CalculationStrategy.WLED,
                    CalculationStrategy.LUT,
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

SCHEMA_POWER_FIXED = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_STATES_POWER): selector.ObjectSelector(),
    }
)

SCHEMA_POWER_LINEAR = vol.Schema(
    {
        vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
        vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
        vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
        vol.Optional(CONF_CALIBRATE): selector.ObjectSelector(),
    }
)

SCHEMA_POWER_LUT_AUTODISCOVERED = vol.Schema(
    {vol.Optional(CONF_CONFIRM_AUTODISCOVERED_MODEL, default=True): bool}
)

SCHEMA_POWER_ADVANCED = vol.Schema(
    {vol.Optional(CONF_CALCULATION_ENABLED_CONDITION): selector.TemplateSelector()}
)

SCHEMA_GROUP = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_UNIQUE_ID): selector.TextSelector(),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PowerCalc."""

    VERSION = 1

    def __init__(self):
        """Initialize options flow."""
        self.sensor_config: dict[str, Any] = {}
        self.selected_sensor_type: str | None = None
        self.name: str | None = None
        self.source_entity: SourceEntity | None = None
        self.source_entity_id: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""

        return self.async_show_menu(step_id="user", menu_options=SENSOR_TYPE_MENU)

    async def async_step_virtual_power(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        if user_input is not None:
            self.source_entity_id = user_input[CONF_ENTITY_ID]
            self.source_entity = await create_source_entity(
                self.source_entity_id, self.hass
            )
            unique_id = (
                user_input.get(CONF_UNIQUE_ID)
                or self.source_entity.unique_id
                or self.source_entity_id
            )

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.name = user_input.get(CONF_NAME) or self.source_entity.name
            self.selected_sensor_type = SensorType.VIRTUAL_POWER
            self.sensor_config.update(user_input)

            if user_input.get(CONF_MODE) == CalculationStrategy.FIXED:
                return await self.async_step_fixed()

            if user_input.get(CONF_MODE) == CalculationStrategy.LINEAR:
                return await self.async_step_linear()

            if user_input.get(CONF_MODE) == CalculationStrategy.WLED:
                return await self.async_step_wled()

            if user_input.get(CONF_MODE) == CalculationStrategy.LUT:
                return await self.async_step_lut()

        return self.async_show_form(
            step_id="virtual_power",
            data_schema=_create_virtual_power_schema(self.hass),
            errors={},
        )

    async def async_step_daily_energy(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        errors = _validate_daily_energy_input(user_input)

        if user_input is not None and not errors:
            unique_id = user_input.get(CONF_UNIQUE_ID) or user_input.get(CONF_NAME)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.selected_sensor_type = SensorType.DAILY_ENERGY
            self.name = user_input.get(CONF_NAME)

            self.sensor_config.update(
                {CONF_DAILY_FIXED_ENERGY: _build_daily_energy_config(user_input)}
            )
            return self.create_config_entry()

        return self.async_show_form(
            step_id="daily_energy",
            data_schema=SCHEMA_DAILY_ENERGY,
            errors=errors,
        )

    async def async_step_group(self, user_input: dict[str, str] = None) -> FlowResult:
        self.selected_sensor_type = SensorType.GROUP
        errors = _validate_group_input(user_input)
        if user_input is not None:
            self.name = user_input.get(CONF_NAME)
            self.sensor_config.update(user_input)
            if not errors:
                return self.create_config_entry()

        group_schema = SCHEMA_GROUP.extend(
            _create_group_options_schema(self.hass).schema
        )
        return self.async_show_form(
            step_id="group",
            data_schema=group_schema,
            errors=errors,
        )

    async def async_step_fixed(self, user_input: dict[str, str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            if user_input.get(CONF_POWER_TEMPLATE):
                user_input[CONF_POWER] = user_input.get(CONF_POWER_TEMPLATE)
            self.sensor_config.update({CONF_FIXED: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return await self.async_step_power_advanced()

        return self.async_show_form(
            step_id="fixed",
            data_schema=SCHEMA_POWER_FIXED,
            errors=errors,
        )

    async def async_step_linear(self, user_input: dict[str, str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_LINEAR: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return await self.async_step_power_advanced()

        return self.async_show_form(
            step_id="linear",
            data_schema=_create_linear_schema(self.source_entity_id),
            errors=errors,
        )

    async def async_step_wled(self, user_input: dict[str, str] = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_WLED: user_input})
            errors = await self.validate_strategy_config()
            if not errors:
                return await self.async_step_power_advanced()

        return self.async_show_form(
            step_id="wled",
            data_schema=SCHEMA_POWER_WLED,
            errors=errors,
        )

    async def async_step_lut(self, user_input: dict[str, str] = None) -> FlowResult:
        """Try to autodiscover manufacturer/model first. Ask the user to confirm this or forward to manual configuration"""
        if user_input is not None:
            if user_input.get(CONF_CONFIRM_AUTODISCOVERED_MODEL):
                return await self.async_step_power_advanced()

            return await self.async_step_lut_manufacturer()

        power_profile = None
        if self.source_entity.entity_entry:
            try:
                power_profile = await get_power_profile(
                    self.hass, {}, self.source_entity.entity_entry
                )
            except ModelNotSupported:
                power_profile = None
        if power_profile:
            return self.async_show_form(
                step_id="lut",
                description_placeholders={
                    "manufacturer": power_profile.manufacturer,
                    "model": power_profile.model,
                },
                data_schema=SCHEMA_POWER_LUT_AUTODISCOVERED,
                errors={},
            )

        return await self.async_step_lut_manufacturer()

    async def async_step_lut_manufacturer(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        """Ask the user to select the manufacturer"""
        if user_input is not None:
            self.sensor_config.update(
                {CONF_MANUFACTURER: user_input.get(CONF_MANUFACTURER)}
            )
            return await self.async_step_lut_model()

        schema = _create_lut_schema_manufacturer(self.hass)
        return self.async_show_form(
            step_id="lut_manufacturer",
            data_schema=schema,
            errors={},
        )

    async def async_step_lut_model(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update({CONF_MODEL: user_input.get(CONF_MODEL)})
            library = ProfileLibrary(self.hass)
            profile = await library.get_profile(
                ModelInfo(
                    self.sensor_config.get(CONF_MANUFACTURER),
                    self.sensor_config.get(CONF_MODEL),
                )
            )
            sub_profiles = profile.get_sub_profiles()
            if sub_profiles:
                return await self.async_step_lut_subprofile()
            errors = await self.validate_strategy_config()
            if not errors:
                return await self.async_step_power_advanced()

        return self.async_show_form(
            step_id="lut_model",
            data_schema=_create_lut_schema_model(
                self.hass, self.sensor_config.get(CONF_MANUFACTURER)
            ),
            description_placeholders={
                "supported_models_link": "https://github.com/bramstroker/homeassistant-powercalc/blob/master/docs/supported_models.md"
            },
            errors=errors,
        )

    async def async_step_lut_subprofile(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        errors = {}
        if user_input is not None:
            # Append the sub profile to the model
            model = f"{self.sensor_config.get(CONF_MODEL)}/{user_input.get(CONF_SUB_PROFILE)}"
            self.sensor_config[CONF_MODEL] = model
            errors = await self.validate_strategy_config()
            if not errors:
                return await self.async_step_power_advanced()

        model_info = ModelInfo(
            self.sensor_config.get(CONF_MANUFACTURER),
            self.sensor_config.get(CONF_MODEL),
        )
        return self.async_show_form(
            step_id="lut_subprofile",
            data_schema=await _create_lut_schema_subprofile(self.hass, model_info),
            errors=errors,
        )

    async def async_step_power_advanced(
        self, user_input: dict[str, str] = None
    ) -> FlowResult:
        errors = {}
        if user_input is not None:
            self.sensor_config.update(user_input)
            return self.create_config_entry()

        return self.async_show_form(
            step_id="power_advanced",
            data_schema=SCHEMA_POWER_ADVANCED,
            errors=errors,
        )

    async def validate_strategy_config(self) -> dict:
        strategy_name = self.sensor_config.get(CONF_MODE)
        strategy = await _create_strategy_object(
            self.hass, strategy_name, self.sensor_config, self.source_entity
        )
        try:
            await strategy.validate_config()
        except StrategyConfigurationError as error:
            translation = error.get_config_flow_translate_key()
            if translation is None:
                translation = "unknown"
            _LOGGER.error(str(error))
            return {"base": translation}
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
        return self.async_create_entry(title=self.name, data=self.sensor_config)


class OptionsFlowHandler(OptionsFlow):
    """Handle an option flow for PowerCalc."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.current_config: dict = dict(config_entry.data)
        self.sensor_type: SensorType = (
            self.current_config.get(CONF_SENSOR_TYPE) or SensorType.VIRTUAL_POWER
        )
        self.source_entity_id: str | None = self.current_config.get(CONF_ENTITY_ID)
        self.source_entity: SourceEntity | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""

        self.current_config = dict(self.config_entry.data)
        if self.source_entity_id:
            self.source_entity = await create_source_entity(
                self.source_entity_id, self.hass
            )

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
            generic_option_schema = SCHEMA_POWER_OPTIONS.extend(
                SCHEMA_POWER_ADVANCED.schema
            )
            generic_options = {}
            for key, val in generic_option_schema.schema.items():
                if isinstance(key, vol.Marker):
                    key = key.schema
                if key in user_input:
                    generic_options[key] = user_input.get(key)

            self.current_config.update(generic_options)

            strategy = self.current_config.get(CONF_MODE)

            strategy_options = _build_strategy_config(
                strategy, self.source_entity_id, user_input
            )

            if strategy != CalculationStrategy.LUT:
                self.current_config.update({strategy: strategy_options})

            strategy_object = await _create_strategy_object(
                self.hass, strategy, self.current_config, self.source_entity
            )
            try:
                await strategy_object.validate_config()
            except StrategyConfigurationError as error:
                return {"base": error.get_config_flow_translate_key()}

        if self.sensor_type == SensorType.GROUP:
            self.current_config.update(user_input)

        self.hass.config_entries.async_update_entry(
            self.config_entry, data=self.current_config
        )
        return {}

    def build_options_schema(self) -> vol.Schema:
        """Build the options schema. depending on the selected sensor type"""

        strategy_options = {}
        data_schema = {}
        if self.sensor_type == SensorType.VIRTUAL_POWER:
            strategy: str = self.current_config.get(CONF_MODE)
            strategy_schema = _get_strategy_schema(strategy, self.source_entity_id)
            data_schema = SCHEMA_POWER_OPTIONS.extend(strategy_schema.schema).extend(
                SCHEMA_POWER_ADVANCED.schema
            )
            strategy_options = self.current_config.get(strategy) or {}

        if self.sensor_type == SensorType.DAILY_ENERGY:
            data_schema = SCHEMA_DAILY_ENERGY_OPTIONS
            strategy_options = self.current_config[CONF_DAILY_FIXED_ENERGY]

        if self.sensor_type == SensorType.GROUP:
            data_schema = _create_group_options_schema(self.hass)

        data_schema = _fill_schema_defaults(
            data_schema, self.current_config | strategy_options
        )
        return data_schema


async def _create_strategy_object(
    hass: HomeAssistant, strategy: str, config: dict, source_entity: SourceEntity
) -> PowerCalculationStrategyInterface:
    """Create the calculation strategy object"""
    factory = PowerCalculatorStrategyFactory(hass)
    power_profile = None
    if strategy == CalculationStrategy.LUT:
        power_profile = await ProfileLibrary.factory(hass).get_profile(
            ModelInfo(config.get(CONF_MANUFACTURER), config.get(CONF_MODEL))
        )
    return factory.create(config, strategy, power_profile, source_entity)


def _get_strategy_schema(strategy: str, source_entity_id: str) -> vol.Schema:
    """Get the config schema for a given power calculation strategy"""
    if strategy == CalculationStrategy.FIXED:
        return SCHEMA_POWER_FIXED
    if strategy == CalculationStrategy.LINEAR:
        return _create_linear_schema(source_entity_id)
    if strategy == CalculationStrategy.WLED:
        return SCHEMA_POWER_WLED
    if strategy == CalculationStrategy.LUT:
        return vol.Schema({})


def _create_virtual_power_schema(hass: HomeAssistant) -> vol.Schema:
    base_schema: vol.Schema = SCHEMA_POWER_BASE.extend(
        {vol.Optional(CONF_GROUP): _create_group_selector(hass)}
    )
    return base_schema.extend(SCHEMA_POWER_OPTIONS.schema)


def _create_group_options_schema(hass: HomeAssistant) -> vol.Schema:
    """Create config schema for groups"""
    member_sensors = [
        selector.SelectOptionDict(
            value=config_entry.entry_id, label=config_entry.data.get(CONF_NAME)
        )
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.VIRTUAL_POWER
        and config_entry.unique_id is not None
    ]
    member_sensor_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=member_sensors,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    return vol.Schema(
        {
            vol.Optional(CONF_GROUP_MEMBER_SENSORS): member_sensor_selector,
            vol.Optional(CONF_GROUP_POWER_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.POWER,
                    multiple=True,
                )
            ),
            vol.Optional(CONF_GROUP_ENERGY_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.ENERGY,
                    multiple=True,
                )
            ),
            vol.Optional(CONF_SUB_GROUPS): _create_group_selector(hass, multiple=True),
            vol.Optional(
                CONF_CREATE_UTILITY_METERS, default=False
            ): selector.BooleanSelector(),
            vol.Optional(CONF_HIDE_MEMBERS, default=False): selector.BooleanSelector(),
        }
    )


def _create_group_selector(
    hass: HomeAssistant, multiple: bool = False
) -> selector.SelectSelector:
    options = [
        selector.SelectOptionDict(
            value=config_entry.entry_id, label=config_entry.data.get(CONF_NAME)
        )
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if config_entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP
    ]

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=multiple,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _validate_group_input(user_input: dict[str, str] = None) -> dict:
    """Validate the group form"""
    if not user_input:
        return {}
    errors = {}

    if (
        CONF_SUB_GROUPS not in user_input
        and CONF_GROUP_POWER_ENTITIES not in user_input
        and CONF_GROUP_ENERGY_ENTITIES not in user_input
        and CONF_GROUP_MEMBER_SENSORS not in user_input
    ):
        errors["base"] = "group_mandatory"

    return errors


def _create_linear_schema(source_entity_id: str) -> vol.Schema:
    """Create the config schema for linear strategy"""
    return SCHEMA_POWER_LINEAR.extend(
        {
            vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(
                selector.AttributeSelectorConfig(entity_id=source_entity_id)
            )
        }
    )


def _create_lut_schema_manufacturer(hass: HomeAssistant) -> vol.Schema:
    """Create LUT schema"""
    library = ProfileLibrary(hass)
    manufacturers = [
        selector.SelectOptionDict(value=manufacturer, label=manufacturer)
        for manufacturer in library.get_manufacturer_listing()
    ]
    return vol.Schema(
        {
            vol.Required(CONF_MANUFACTURER): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=manufacturers, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        }
    )


def _create_lut_schema_model(hass: HomeAssistant, manufacturer: str) -> vol.Schema:
    """Create LUT schema"""
    library = ProfileLibrary(hass)
    models = [
        selector.SelectOptionDict(value=model, label=model)
        for model in library.get_model_listing(manufacturer)
    ]
    return vol.Schema(
        {
            vol.Required(CONF_MODEL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=models, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        }
    )


async def _create_lut_schema_subprofile(
    hass: HomeAssistant, model_info: ModelInfo
) -> vol.Schema:
    """Create LUT schema"""
    library = ProfileLibrary(hass)
    profile = await library.get_profile(model_info)
    sub_profiles = [
        selector.SelectOptionDict(value=sub_profile, label=sub_profile)
        for sub_profile in profile.get_sub_profiles()
    ]
    return vol.Schema(
        {
            vol.Required(CONF_SUB_PROFILE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sub_profiles, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        }
    )


def _build_strategy_config(
    strategy: str, source_entity_id: str, user_input: dict[str, str] = None
) -> dict[str, Any]:
    """Build the config dict needed for the configured strategy"""
    strategy_schema = _get_strategy_schema(strategy, source_entity_id)
    strategy_options = {}
    for key in strategy_schema.schema.keys():
        if user_input.get(key) is None:
            continue
        strategy_options[str(key)] = user_input.get(key)
    return strategy_options


def _build_daily_energy_config(user_input: dict[str, str] = None) -> dict[str, Any]:
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

    if CONF_VALUE not in user_input and CONF_VALUE_TEMPLATE not in user_input:
        errors["base"] = "daily_energy_mandatory"

    return errors


def _fill_schema_defaults(data_schema: vol.Schema, options: dict[str, str]):
    """Make a copy of the schema with suggested values set to saved options"""
    schema = {}
    for key, val in data_schema.schema.items():
        new_key = key
        if key in options and isinstance(key, vol.Marker):
            if (
                isinstance(key, vol.Optional)
                and callable(key.default)
                and key.default()
            ):
                new_key = vol.Optional(key.schema, default=options.get(key))
            else:
                new_key = copy.copy(key)
                new_key.description = {"suggested_value": options.get(key)}
        schema[new_key] = val
    data_schema = vol.Schema(schema)
    return data_schema
