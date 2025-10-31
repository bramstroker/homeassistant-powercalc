"""Config flow for Powercalc integration."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, cast

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryBaseFlow,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_DEVICE,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    Platform,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.const import (
    __version__ as HAVERSION,  # noqa
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector, translation
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.helpers.selector import TextSelector
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_AUTOSTART,
    CONF_AVAILABILITY_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_GAMMA_CURVE,
    CONF_GROUP,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_NEW_GROUP,
    CONF_ON_TIME,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_POWER_TEMPLATE,
    CONF_REPEAT,
    CONF_SELF_USAGE_INCLUDED,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_STATE_TRIGGER,
    CONF_STATES_POWER,
    CONF_SUB_PROFILE,
    CONF_UNAVAILABLE_POWER,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    CONF_VARIABLES,
    DISCOVERY_POWER_PROFILES,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DUMMY_ENTITY_ID,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    LIBRARY_URL,
    CalculationStrategy,
    GroupType,
    SensorType,
)
from .discovery import get_power_profile_by_source_entity
from .errors import ModelNotSupportedError, StrategyConfigurationError
from .flow_helper.common import PowercalcFormStep, Step, fill_schema_defaults
from .flow_helper.dynamic_field_builder import build_dynamic_field_schema
from .flow_helper.flows.global_configuration import GlobalConfigurationConfigFlow, GlobalConfigurationFlow, GlobalConfigurationOptionsFlow
from .flow_helper.flows.group import (
    GroupConfigFlow,
    GroupOptionsFlow,
    create_group_selector,
)
from .flow_helper.schema import (
    SCHEMA_ENERGY_OPTIONS,
    SCHEMA_ENERGY_SENSOR_TOGGLE,
    SCHEMA_UTILITY_METER_OPTIONS,
    SCHEMA_UTILITY_METER_TOGGLE,
    build_sub_profile_schema,
)
from .power_profile.factory import get_power_profile
from .power_profile.library import ModelInfo, ProfileLibrary
from .power_profile.power_profile import DEVICE_TYPE_DOMAIN, DOMAIN_DEVICE_TYPE_MAPPING, SUPPORTED_DOMAINS, DeviceType, DiscoveryBy, PowerProfile
from .sensors.daily_energy import DEFAULT_DAILY_UPDATE_FREQUENCY
from .sensors.group.config_entry_utils import get_group_entries
from .strategy.factory import PowerCalculatorStrategyFactory
from .strategy.wled import CONFIG_SCHEMA as SCHEMA_POWER_WLED

_LOGGER = logging.getLogger(__name__)

CONF_CONFIRM_AUTODISCOVERED_MODEL = "confirm_autodisovered_model"


MENU_SENSOR_TYPE = [
    Step.VIRTUAL_POWER,
    Step.MENU_LIBRARY,
    Step.MENU_GROUP,
    Step.DAILY_ENERGY,
    Step.REAL_POWER,
]

MENU_OPTIONS = [
    Step.FIXED,
    Step.LINEAR,
    Step.MULTI_SWITCH,
    Step.PLAYBOOK,
    Step.WLED,
]

STRATEGY_STEP_MAPPING: dict[CalculationStrategy, Step] = {
    CalculationStrategy.FIXED: Step.FIXED,
    CalculationStrategy.LINEAR: Step.LINEAR,
    CalculationStrategy.MULTI_SWITCH: Step.MULTI_SWITCH,
    CalculationStrategy.PLAYBOOK: Step.PLAYBOOK,
    CalculationStrategy.WLED: Step.WLED,
}

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

SCHEMA_POWER_LIBRARY = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
        vol.Optional(CONF_NAME): selector.TextSelector(),
    },
)

SCHEMA_POWER_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_POWER_OPTIONS_LIBRARY = vol.Schema(
    {
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_POWER_BASE = vol.Schema(
    {
        vol.Optional(CONF_NAME): selector.TextSelector(),
    },
)

STRATEGY_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            CalculationStrategy.FIXED,
            CalculationStrategy.LINEAR,
            CalculationStrategy.MULTI_SWITCH,
            CalculationStrategy.PLAYBOOK,
            CalculationStrategy.WLED,
            CalculationStrategy.LUT,
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    ),
)

SCHEMA_POWER_FIXED = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_STATES_POWER): selector.ObjectSelector(),
    },
)

SCHEMA_POWER_SMART_SWITCH = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_SELF_USAGE_INCLUDED): selector.BooleanSelector(),
    },
)

SCHEMA_POWER_LINEAR = vol.Schema(
    {
        vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
        vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
        vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
        vol.Optional(CONF_CALIBRATE): selector.ObjectSelector(),
    },
)

SCHEMA_POWER_MULTI_SWITCH_MANUAL = vol.Schema(
    {
        vol.Required(CONF_POWER): vol.Coerce(float),
        vol.Required(CONF_POWER_OFF): vol.Coerce(float),
    },
)

SCHEMA_POWER_PLAYBOOK = vol.Schema(
    {
        vol.Optional(CONF_PLAYBOOKS): selector.ObjectSelector(),
        vol.Optional(CONF_REPEAT): selector.BooleanSelector(),
        vol.Optional(CONF_AUTOSTART): selector.TextSelector(),
        vol.Optional(CONF_STATE_TRIGGER): selector.ObjectSelector(),
    },
)

SCHEMA_POWER_AUTODISCOVERED = vol.Schema(
    {vol.Optional(CONF_CONFIRM_AUTODISCOVERED_MODEL, default=True): bool},
)

SCHEMA_POWER_ADVANCED = vol.Schema(
    {
        vol.Optional(CONF_CALCULATION_ENABLED_CONDITION): selector.TemplateSelector(),
        vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): selector.BooleanSelector(),
        vol.Optional(CONF_UNAVAILABLE_POWER): vol.Coerce(float),
        vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
        vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY): selector.BooleanSelector(),
    },
)


STRATEGY_SCHEMAS: dict[CalculationStrategy, vol.Schema] = {
    CalculationStrategy.FIXED: SCHEMA_POWER_FIXED,
    CalculationStrategy.PLAYBOOK: SCHEMA_POWER_PLAYBOOK,
    CalculationStrategy.WLED: SCHEMA_POWER_WLED,
}


# noinspection PyTypeChecker
class PowercalcCommonFlow(ABC, ConfigEntryBaseFlow):
    def __init__(self) -> None:
        """Initialize options flow."""
        self.sensor_config: ConfigType = {}
        self.global_config: ConfigType = {}
        self.source_entity: SourceEntity | None = None
        self.source_entity_id: str | None = None
        self.selected_profile: PowerProfile | None = None
        self.selected_sub_profile: str | None = None
        self.is_library_flow: bool = False
        self.skip_advanced_step: bool = False
        self.selected_sensor_type: SensorType | None = None
        self.is_options_flow: bool = isinstance(self, OptionsFlow)
        self.strategy: CalculationStrategy | None = None
        self.name: str | None = None
        self.handled_steps: list[Step] = []
        self.global_config_common_flow = GlobalConfigurationFlow(self)
        super().__init__()

    @abstractmethod
    @callback
    def persist_config_entry(self) -> FlowResult:
        pass  # pragma: no cover

    async def validate_strategy_config(self, user_input: dict[str, Any] | None = None) -> None:
        """Validate the strategy config."""
        strategy_name = CalculationStrategy(
            self.sensor_config.get(CONF_MODE) or self.selected_profile.calculation_strategy,  # type: ignore
        )
        factory = PowerCalculatorStrategyFactory(self.hass)
        try:
            await factory.create(user_input or self.sensor_config, strategy_name, self.selected_profile, self.source_entity)  # type: ignore
        except StrategyConfigurationError as error:
            _LOGGER.error(str(error))
            raise SchemaFlowError(error.get_config_flow_translate_key() or "unknown") from error

    def create_strategy_schema(self) -> vol.Schema:
        """Get the config schema for a given power calculation strategy."""
        if not self.strategy:
            raise ValueError("No strategy selected")  # pragma: no cover

        if hasattr(self, f"create_schema_{self.strategy.lower()}"):
            return getattr(self, f"create_schema_{self.strategy.lower()}")()  # type: ignore

        return STRATEGY_SCHEMAS[self.strategy]

    def create_schema_linear(self) -> vol.Schema:
        """Create the config schema for linear strategy."""
        return SCHEMA_POWER_LINEAR.extend(  # type: ignore
            {
                vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(
                    selector.AttributeSelectorConfig(
                        entity_id=self.source_entity_id,  # type: ignore
                        hide_attributes=[],
                    ),
                ),
            },
        )

    def create_schema_multi_switch(self) -> vol.Schema:
        """Create the config schema for multi switch strategy."""

        switch_domains = [str(Platform.SWITCH), str(Platform.LIGHT), str(Platform.COVER)]
        if self.source_entity and self.source_entity.device_entry:
            entity_selector = self.create_device_entity_selector(switch_domains, multiple=True)
        else:
            entity_selector = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=switch_domains,
                    multiple=True,
                ),
            )

        default_entities = entity_selector.config.get("include_entities", [])
        schema = vol.Schema({vol.Optional(CONF_ENTITIES, default=default_entities): entity_selector})

        if not self.is_library_flow:
            schema = schema.extend(SCHEMA_POWER_MULTI_SWITCH_MANUAL.schema)

        return schema

    def create_schema_virtual_power(
        self,
    ) -> vol.Schema:
        """Create the config schema for virtual power sensor."""
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTITY_ID): self.create_source_entity_selector(),
            },
        ).extend(SCHEMA_POWER_BASE.schema)
        if not self.is_library_flow:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_MODE,
                        default=CalculationStrategy.FIXED,
                    ): STRATEGY_SELECTOR,
                },
            )
            options_schema = SCHEMA_POWER_OPTIONS
        else:
            options_schema = SCHEMA_POWER_OPTIONS_LIBRARY

        power_options = fill_schema_defaults(
            options_schema,
            self.global_config_common_flow.get_global_powercalc_config(),
        )
        return schema.extend(power_options.schema)  # type: ignore

    def create_source_entity_selector(
        self,
    ) -> selector.EntitySelector:
        """Create the entity selector for the source entity."""
        if self.is_library_flow:
            return selector.EntitySelector(
                selector.EntitySelectorConfig(domain=list(SUPPORTED_DOMAINS)),
            )
        return selector.EntitySelector()

    def create_device_entity_selector(self, domains: list[str], multiple: bool = False) -> selector.EntitySelector:
        entity_registry = er.async_get(self.hass)
        if self.source_entity and self.source_entity.device_entry:
            entities = [
                entity.entity_id
                for entity in entity_registry.entities.get_entries_for_device_id(self.source_entity.device_entry.id)
                if entity.domain in domains
            ]
        else:
            entities = []

        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=domains,
                multiple=multiple,
                include_entities=entities,
            ),
        )

    def build_strategy_config(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the config dict needed for the configured strategy."""
        strategy_schema = self.create_strategy_schema()
        strategy_options: dict[str, Any] = {}
        for key in strategy_schema.schema:
            if user_input.get(key) is None:
                continue
            strategy_options[str(key)] = user_input.get(key)
        return strategy_options

    @staticmethod
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

    async def handle_form_step(
        self,
        form_step: PowercalcFormStep,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the current step."""
        if user_input is not None:
            if form_step.validate_user_input is not None:
                try:
                    user_input = await form_step.validate_user_input(user_input)
                except SchemaFlowError as exc:
                    return await self._show_form(form_step, exc)

            if CONF_NAME in user_input:
                self.name = user_input[CONF_NAME]
            self.sensor_config.update(user_input)

            self.handled_steps.append(form_step.step)
            next_step = form_step.next_step
            if callable(form_step.next_step):
                next_step = await form_step.next_step(user_input)
            if not next_step:
                return await self.handle_final_steps(
                    skip_advanced=not form_step.continue_advanced_step,
                    skip_utility_meter_options=not form_step.continue_utility_meter_options_step,
                )

            return await getattr(self, f"async_step_{next_step}")()  # type: ignore

        return await self._show_form(form_step)

    async def handle_final_steps(
        self,
        skip_advanced: bool = False,
        skip_utility_meter_options: bool = False,
    ) -> FlowResult:
        """Handle the final steps of the flow if needed and persist the config entry."""
        if not skip_advanced and self.selected_sensor_type == SensorType.VIRTUAL_POWER:
            return await self.async_step_power_advanced()
        if not skip_utility_meter_options and self.sensor_config.get(CONF_CREATE_UTILITY_METERS):
            return await self.async_step_utility_meter_options()
        return self.persist_config_entry()

    def get_global_powercalc_config(self) -> ConfigType:
        return self.global_config_common_flow.get_global_powercalc_config()

    async def _show_form(self, form_step: PowercalcFormStep, error: SchemaFlowError | None = None) -> FlowResult:
        # Show form for next step
        last_step = None
        if not callable(form_step.next_step):
            last_step = form_step.next_step is None

        schema = await self._get_schema(form_step)
        # noinspection PyTypeChecker
        return self.async_show_form(
            step_id=form_step.step,
            data_schema=fill_schema_defaults(
                schema,
                {**self.sensor_config, **self.global_config_common_flow.get_global_powercalc_config()},
            ),
            errors={"base": str(error)} if error else {},
            last_step=last_step,
            **(form_step.form_kwarg or {}),
        )

    async def _get_schema(self, form_step: PowercalcFormStep) -> vol.Schema:
        if isinstance(form_step.schema, vol.Schema):
            return form_step.schema
        return await form_step.schema()

    async def async_step_manufacturer(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Ask the user to select the manufacturer."""

        async def _create_schema() -> vol.Schema:
            """Create manufacturer schema."""
            library = await ProfileLibrary.factory(self.hass)
            device_types = DOMAIN_DEVICE_TYPE_MAPPING.get(self.source_entity.domain, set()) if self.source_entity else None
            manufacturers = [
                selector.SelectOptionDict(value=manufacturer[0], label=manufacturer[1])
                for manufacturer in await library.get_manufacturer_listing(device_types)
            ]
            return vol.Schema(
                {
                    vol.Required(CONF_MANUFACTURER, default=self.sensor_config.get(CONF_MANUFACTURER)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=manufacturers,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                },
            )

        # noinspection PyTypeChecker
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.MANUFACTURER,
                schema=_create_schema,
                next_step=Step.MODEL,
            ),
            user_input,
        )

    async def async_step_model(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Ask the user to select the model."""

        async def _validate(user_input: dict[str, Any]) -> dict[str, str]:
            library = await ProfileLibrary.factory(self.hass)
            profile = await library.get_profile(
                ModelInfo(
                    str(self.sensor_config.get(CONF_MANUFACTURER)),
                    str(user_input.get(CONF_MODEL)),
                ),
                self.source_entity,
            )
            self.selected_profile = profile
            if self.selected_profile and not await self.selected_profile.needs_user_configuration:
                await self.validate_strategy_config()
            return user_input

        async def _create_schema() -> vol.Schema:
            """Create model schema."""
            manufacturer = str(self.sensor_config.get(CONF_MANUFACTURER))
            library = await ProfileLibrary.factory(self.hass)
            device_types = DOMAIN_DEVICE_TYPE_MAPPING.get(self.source_entity.domain, set()) if self.source_entity else None
            models = [selector.SelectOptionDict(value=model, label=model) for model in await library.get_model_listing(manufacturer, device_types)]
            model = self.selected_profile.model if self.selected_profile else self.sensor_config.get(CONF_MODEL)
            return vol.Schema(
                {
                    vol.Required(CONF_MODEL, description={"suggested_value": model}, default=model): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=models,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                },
            )

        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.MODEL,
                schema=_create_schema,
                next_step=Step.POST_LIBRARY,
                validate_user_input=_validate,
                form_kwarg={"description_placeholders": {"supported_models_link": LIBRARY_URL}},
            ),
            user_input,
        )

    async def async_step_post_library(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """
        Handles the logic after the user either selected manufacturer/model himself or confirmed autodiscovered.
        Forwards to the next step in the flow.
        """
        if not self.selected_profile:
            return self.async_abort(reason="model_not_supported")  # pragma: no cover

        if Step.LIBRARY_CUSTOM_FIELDS not in self.handled_steps and self.selected_profile.has_custom_fields:
            return await self.async_step_library_custom_fields()

        if Step.AVAILABILITY_ENTITY not in self.handled_steps and self.selected_profile.discovery_by == DiscoveryBy.DEVICE:
            result = await self.async_step_availability_entity()
            if result:
                return result

        if Step.SUB_PROFILE not in self.handled_steps and await self.selected_profile.requires_manual_sub_profile_selection:
            return await self.async_step_sub_profile()

        if (
            Step.SMART_SWITCH not in self.handled_steps
            and self.selected_profile.device_type == DeviceType.SMART_SWITCH
            and self.selected_profile.calculation_strategy == CalculationStrategy.FIXED
        ):
            return await self.async_step_smart_switch()

        if Step.FIXED not in self.handled_steps and self.selected_profile.needs_fixed_config:  # pragma: no cover
            return await self.async_step_fixed()

        if Step.LINEAR not in self.handled_steps and self.selected_profile.needs_linear_config:
            return await self.async_step_linear()

        if Step.MULTI_SWITCH not in self.handled_steps and self.selected_profile.calculation_strategy == CalculationStrategy.MULTI_SWITCH:
            return await self.async_step_multi_switch()

        return await self.async_step_assign_groups()

    async def async_step_availability_entity(self, user_input: dict[str, Any] | None = None) -> FlowResult | None:
        """Handle the flow for availability entity."""
        domains = DEVICE_TYPE_DOMAIN[self.selected_profile.device_type]  # type: ignore
        entity_selector = self.create_device_entity_selector(
            list(domains) if isinstance(domains, set) else [domains],
        )
        try:
            first_entity = entity_selector.config["include_entities"][0]
        except IndexError:
            # Skip step if no entities are available
            self.handled_steps.append(Step.AVAILABILITY_ENTITY)
            return None
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.AVAILABILITY_ENTITY,
                schema=vol.Schema(
                    {
                        vol.Optional(CONF_AVAILABILITY_ENTITY, default=first_entity): entity_selector,
                    },
                ),
                next_step=Step.POST_LIBRARY,
            ),
            user_input,
        )

    async def async_step_library_custom_fields(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for custom fields."""

        async def _process_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
            return {CONF_VARIABLES: user_input}

        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.LIBRARY_CUSTOM_FIELDS,
                schema=build_dynamic_field_schema(self.selected_profile),  # type: ignore
                next_step=Step.POST_LIBRARY,
                validate_user_input=_process_user_input,
            ),
            user_input,
        )

    async def async_step_sub_profile(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for sub profile selection."""

        async def _validate(user_input: dict[str, Any]) -> dict[str, str]:
            return {CONF_MODEL: f"{self.sensor_config.get(CONF_MODEL)}/{user_input.get(CONF_SUB_PROFILE)}"}

        library = await ProfileLibrary.factory(self.hass)
        profile = await library.get_profile(
            ModelInfo(
                str(self.sensor_config.get(CONF_MANUFACTURER)),
                str(self.sensor_config.get(CONF_MODEL)),
            ),
            self.source_entity,
            process_variables=False,
        )
        remarks = profile.config_flow_sub_profile_remarks
        if remarks:
            remarks = "\n\n" + remarks

        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.SUB_PROFILE,
                schema=await build_sub_profile_schema(profile, self.selected_sub_profile),
                next_step=Step.POWER_ADVANCED,
                validate_user_input=_validate,
                form_kwarg={
                    "description_placeholders": {
                        "entity_id": self.source_entity_id,
                        "remarks": remarks,
                    },
                },
            ),
            user_input,
        )

    async def async_step_assign_groups(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for assigning groups."""
        group_entries = get_group_entries(self.hass, GroupType.CUSTOM)
        if not group_entries:
            return await self.handle_final_steps()

        schema = vol.Schema(
            {
                vol.Optional(CONF_GROUP): create_group_selector(self.hass, group_entries=group_entries),
                vol.Optional(CONF_NEW_GROUP): TextSelector(),
            },
        )

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            groups = user_input.get(CONF_GROUP) or []
            new_group = user_input.get(CONF_NEW_GROUP)
            if new_group:
                groups.append(new_group)
            return {CONF_GROUP: groups}

        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.ASSIGN_GROUPS,
                schema=schema,
                continue_advanced_step=True,
                continue_utility_meter_options_step=True,
                validate_user_input=_validate,
            ),
            user_input,
        )

    async def async_step_power_advanced(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for advanced options."""

        if self.is_options_flow:
            return self.persist_config_entry()  # pragma: no cover

        if user_input is not None or self.skip_advanced_step:
            self.sensor_config.update(user_input or {})
            if self.sensor_config.get(CONF_CREATE_UTILITY_METERS):
                return await self.async_step_utility_meter_options()
            return self.persist_config_entry()

        schema = SCHEMA_POWER_ADVANCED
        if self.sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
            schema = schema.extend(SCHEMA_ENERGY_OPTIONS.schema)

        return self.async_show_form(
            step_id=Step.POWER_ADVANCED,
            data_schema=fill_schema_defaults(
                schema,
                self.global_config_common_flow.get_global_powercalc_config(),
            ),
            errors={},
        )

    async def async_step_smart_switch(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Asks the user for the power of connect appliance for the smart switch."""

        if self.selected_profile and not self.selected_profile.needs_fixed_config:
            return self.persist_config_entry()

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            return {
                CONF_SELF_USAGE_INCLUDED: user_input.get(CONF_SELF_USAGE_INCLUDED),
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: user_input.get(CONF_POWER, 0)},
            }

        self_usage_on = self.selected_profile.standby_power_on if self.selected_profile else 0
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.SMART_SWITCH,
                schema=SCHEMA_POWER_SMART_SWITCH,
                validate_user_input=_validate,
                next_step=Step.POWER_ADVANCED,
                form_kwarg={"description_placeholders": {"self_usage_power": str(self_usage_on)}},
            ),
            user_input,
        )

    async def handle_strategy_step(
        self,
        strategy: CalculationStrategy,
        user_input: dict[str, Any] | None = None,
        validate: Callable[[dict[str, Any]], None] | None = None,
    ) -> FlowResult:
        self.strategy = strategy

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            if validate:
                validate(user_input)
            await self.validate_strategy_config({strategy: user_input})
            return {strategy: user_input}

        schema = self.create_strategy_schema()

        return await self.handle_form_step(
            PowercalcFormStep(
                step=STRATEGY_STEP_MAPPING[strategy],
                schema=schema,
                next_step=Step.ASSIGN_GROUPS,
                validate_user_input=_validate,
            ),
            user_input,
        )

    async def async_step_fixed(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for fixed sensor."""
        return await self.handle_strategy_step(CalculationStrategy.FIXED, user_input)

    async def async_step_linear(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for fixed sensor."""
        return await self.handle_strategy_step(CalculationStrategy.LINEAR, user_input)

    async def async_step_multi_switch(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for multi switch strategy."""
        return await self.handle_strategy_step(CalculationStrategy.MULTI_SWITCH, user_input)

    async def async_step_playbook(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for playbook sensor."""

        def _validate(user_input: dict[str, Any]) -> None:
            if user_input.get(CONF_PLAYBOOKS) is None or len(user_input.get(CONF_PLAYBOOKS)) == 0:  # type: ignore
                raise SchemaFlowError("playbook_mandatory")

        return await self.handle_strategy_step(CalculationStrategy.PLAYBOOK, user_input, _validate)

    async def async_step_wled(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for WLED sensor."""
        return await self.handle_strategy_step(CalculationStrategy.WLED, user_input)

    async def async_step_utility_meter_options(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for utility meter options."""
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.UTILITY_METER_OPTIONS,
                schema=SCHEMA_UTILITY_METER_OPTIONS,
            ),
            user_input,
        )

    async def async_step_global_configuration_energy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        return await self.global_config_common_flow.async_step_global_configuration_energy(user_input)

    async def async_step_global_configuration_utility_meter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        return await self.global_config_common_flow.async_step_global_configuration_utility_meter(user_input)


class PowercalcConfigFlow(PowercalcCommonFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PowerCalc."""

    VERSION = 4

    def __init__(self) -> None:
        """Initialize options flow."""
        self.discovered_profiles: dict[str, PowerProfile] = {}
        self.group_flow = GroupConfigFlow(self)
        self.global_config_flow = GlobalConfigurationConfigFlow(self)
        super().__init__()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return PowercalcOptionsFlow(config_entry)

    @callback
    def abort_if_unique_id_configured(self) -> None:
        self._abort_if_unique_id_configured()

    async def async_step_integration_discovery(
        self,
        discovery_info: DiscoveryInfoType,
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        _LOGGER.debug("Starting discovery flow: %s", discovery_info)

        self.skip_advanced_step = True  # We don't want to ask advanced options when discovered

        await self.async_set_unique_id(discovery_info.get(CONF_UNIQUE_ID, str(uuid.uuid4())))
        self.selected_sensor_type = SensorType.VIRTUAL_POWER
        self.source_entity = discovery_info[DISCOVERY_SOURCE_ENTITY]
        del discovery_info[DISCOVERY_SOURCE_ENTITY]
        if not self.source_entity:
            return self.async_abort(reason="No source entity set")  # pragma: no cover

        self.source_entity_id = self.source_entity.entity_id
        self.name = self.source_entity.name

        power_profiles: list[PowerProfile] = []
        if DISCOVERY_POWER_PROFILES in discovery_info:
            power_profiles = discovery_info[DISCOVERY_POWER_PROFILES]
            self.discovered_profiles = {profile.unique_id: profile for profile in power_profiles}
            if len(power_profiles) == 1:
                self.selected_profile = power_profiles[0]
            del discovery_info[DISCOVERY_POWER_PROFILES]

        self.sensor_config = discovery_info.copy()

        self.context["title_placeholders"] = {
            "name": self.name or "",
            "manufacturer": str(self.sensor_config.get(CONF_MANUFACTURER)),
            "model": str(self.sensor_config.get(CONF_MODEL)),
        }
        self.is_library_flow = True

        if discovery_info.get(CONF_MODE) == CalculationStrategy.WLED:
            return await self.async_step_wled()

        if len(power_profiles) > 1:
            return cast(ConfigFlowResult, await self.async_step_library_multi_profile())

        return cast(ConfigFlowResult, await self.async_step_library())

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""

        self.is_library_flow = False
        global_config_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN,
            ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
        )
        menu = MENU_SENSOR_TYPE.copy()
        if not global_config_entry:
            menu.insert(0, Step.GLOBAL_CONFIGURATION)

        await self.async_set_unique_id(str(uuid.uuid4()))

        return self.async_show_menu(step_id=Step.USER, menu_options=menu)

    async def async_step_menu_library(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the Virtual power (library) step.
        We forward to the virtual_power step, but without the strategy selector displayed.
        """
        self.is_library_flow = True
        return await self.async_step_virtual_power(user_input)

    async def async_step_global_configuration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        return await self.global_config_flow.async_step_global_configuration(user_input)

    async def async_step_virtual_power(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for virtual power sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_strategy = CalculationStrategy(
                user_input.get(CONF_MODE) or CalculationStrategy.LUT,
            )
            entity_id = user_input.get(CONF_ENTITY_ID)
            if selected_strategy is not CalculationStrategy.PLAYBOOK and user_input.get(CONF_NAME) is None and entity_id is None:
                errors[CONF_ENTITY_ID] = "entity_mandatory"

            if not errors:
                self.source_entity_id = str(entity_id or DUMMY_ENTITY_ID)
                self.source_entity = await create_source_entity(
                    self.source_entity_id,
                    self.hass,
                )

                self.name = user_input.get(CONF_NAME) or self.source_entity.name
                self.selected_sensor_type = SensorType.VIRTUAL_POWER
                self.sensor_config.update(user_input)

                return await self.forward_to_strategy_step(selected_strategy)

        return self.async_show_form(
            step_id=Step.VIRTUAL_POWER,
            data_schema=self.create_schema_virtual_power(),
            errors=errors,
            last_step=False,
        )

    async def forward_to_strategy_step(
        self,
        strategy: CalculationStrategy,
    ) -> FlowResult:
        """Forward to the next step based on the selected strategy."""
        step = STRATEGY_STEP_MAPPING.get(strategy)
        if step is None:
            return await self.async_step_library()
        method = getattr(self, f"async_step_{step}")
        return await method()  # type: ignore

    async def async_step_daily_energy(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for daily energy sensor."""
        self.selected_sensor_type = SensorType.DAILY_ENERGY

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            if CONF_VALUE not in user_input and CONF_VALUE_TEMPLATE not in user_input:
                raise SchemaFlowError("daily_energy_mandatory")
            return self.build_daily_energy_config(user_input, SCHEMA_DAILY_ENERGY)

        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.DAILY_ENERGY,
                schema=SCHEMA_DAILY_ENERGY,
                validate_user_input=_validate,
                next_step=Step.ASSIGN_GROUPS,
            ),
            user_input,
        )

    async def async_step_menu_group(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.group_flow.async_step_menu_group()

    async def async_step_group_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for custom group sensor."""
        return await self.group_flow.async_step_group_custom(user_input)

    async def async_step_group_domain(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for domain based group sensor."""
        return await self.group_flow.async_step_group_domain(user_input)

    async def async_step_group_subtract(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for subtract group sensor."""
        return await self.group_flow.async_step_group_subtract(user_input)

    async def async_step_group_tracked_untracked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for tracked/untracked group sensor."""
        return await self.group_flow.async_step_group_tracked_untracked(user_input)

    async def async_step_group_tracked_untracked_auto(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for tracked/untracked group sensor."""
        return await self.group_flow.async_step_group_tracked_untracked_auto(user_input)

    async def async_step_group_tracked_untracked_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for tracked/untracked group sensor."""
        return await self.group_flow.async_step_group_tracked_untracked_manual(user_input)

    async def async_step_library_multi_profile(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """This step gets executed when multiple profiles are found for the source entity."""
        if user_input is not None:
            selected_model: str = user_input.get(CONF_MODEL)  # type: ignore
            selected_profile = self.discovered_profiles.get(selected_model)
            if selected_profile is None:  # pragma: no cover
                return self.async_abort(reason="invalid_profile")
            self.selected_profile = selected_profile
            self.sensor_config.update(
                {
                    CONF_MANUFACTURER: selected_profile.manufacturer,
                    CONF_MODEL: selected_profile.model,
                },
            )
            return await self.async_step_post_library(user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_MODEL): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=profile.unique_id,
                                label=profile.model,
                            )
                            for profile in self.discovered_profiles.values()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            },
        )

        manufacturer = str(self.sensor_config.get(CONF_MANUFACTURER))
        model = str(self.sensor_config.get(CONF_MODEL))
        return self.async_show_form(
            step_id=Step.LIBRARY_MULTI_PROFILE,
            data_schema=schema,
            description_placeholders={
                "library_link": f"{LIBRARY_URL}/?manufacturer={manufacturer}",
                "manufacturer": manufacturer,
                "model": model,
            },
            last_step=False,
        )

    async def async_step_library(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Try to autodiscover manufacturer/model first.
        Ask the user to confirm this or forward to manual library selection.
        """
        if user_input is not None:
            if user_input.get(CONF_CONFIRM_AUTODISCOVERED_MODEL) and self.selected_profile:
                self.sensor_config.update(
                    {
                        CONF_MANUFACTURER: self.selected_profile.manufacturer,
                        CONF_MODEL: self.selected_profile.model,
                    },
                )
                return await self.async_step_post_library(user_input)

            return await self.async_step_manufacturer()

        if self.source_entity and self.source_entity.entity_entry and self.selected_profile is None:
            self.selected_profile = await get_power_profile_by_source_entity(self.hass, self.source_entity)
        if self.selected_profile:
            remarks = self.selected_profile.config_flow_discovery_remarks
            if remarks:
                remarks = "\n\n" + remarks

            translations = translation.async_get_cached_translations(self.hass, self.hass.config.language, "common", DOMAIN)
            if self.selected_profile.discovery_by == DiscoveryBy.DEVICE and self.source_entity and self.source_entity.device_entry:
                source = f"{translations.get(f'component.{DOMAIN}.common.source_device')}: {self.source_entity.device_entry.name}"
            else:
                source = f"{translations.get(f'component.{DOMAIN}.common.source_entity')}: {self.source_entity_id}"

            return self.async_show_form(
                step_id=Step.LIBRARY,
                description_placeholders={
                    "remarks": remarks,  # type: ignore
                    "manufacturer": self.selected_profile.manufacturer,
                    "model": self.selected_profile.model,
                    "source": source,
                },
                data_schema=SCHEMA_POWER_AUTODISCOVERED,
                errors={},
                last_step=False,
            )

        return await self.async_step_manufacturer()

    async def async_step_real_power(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for real power sensor"""

        self.selected_sensor_type = SensorType.REAL_POWER
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.REAL_POWER,
                schema=SCHEMA_REAL_POWER,
                continue_utility_meter_options_step=True,
            ),
            user_input,
        )

    @callback
    def persist_config_entry(self) -> FlowResult:
        """Create the config entry."""
        self.sensor_config.update({CONF_SENSOR_TYPE: self.selected_sensor_type})
        self.sensor_config.update({CONF_NAME: self.name})

        if self.source_entity_id:
            self.sensor_config.update({CONF_ENTITY_ID: self.source_entity_id})

        if (
            self.selected_profile
            and self.source_entity
            and self.source_entity.device_entry
            and self.selected_profile.discovery_by == DiscoveryBy.DEVICE
        ):
            self.sensor_config.update({CONF_DEVICE: self.source_entity.device_entry.id})

        return self.async_create_entry(title=str(self.name), data=self.sensor_config)


class PowercalcOptionsFlow(PowercalcCommonFlow, OptionsFlow):
    """Handle an option flow for PowerCalc."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        if AwesomeVersion(HAVERSION) < "2024.12":
            self.config_entry = config_entry  # pragma: no cover
        self.sensor_config = dict(config_entry.data)
        self.strategy = self.sensor_config.get(CONF_MODE)
        self.group_flow = GroupOptionsFlow(self)
        self.global_config_flow = GlobalConfigurationOptionsFlow(self)

    @callback
    def abort_if_unique_id_configured(self) -> None:
        """Return if unique_id is already configured."""
        return

    async def async_set_unique_id(self, unique_id: str | None, raise_on_progress: bool = True) -> None:
        """Set the unique ID of the flow."""
        return

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle options flow."""
        self.selected_sensor_type = self.sensor_config.get(CONF_SENSOR_TYPE) or SensorType.VIRTUAL_POWER
        self.source_entity_id = self.sensor_config.get(CONF_ENTITY_ID)

        if self.config_entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
            self.global_config = self.global_config_common_flow.get_global_powercalc_config()
            return self.async_show_menu(step_id=Step.INIT, menu_options=self.global_config_flow.build_global_config_menu())

        self.sensor_config = dict(self.config_entry.data)
        if self.source_entity_id:
            self.source_entity = await create_source_entity(
                self.source_entity_id,
                self.hass,
            )
            result = await self.initialize_library_profile()
            if result:
                return result

        return self.async_show_menu(step_id=Step.INIT, menu_options=self.build_menu())

    async def initialize_library_profile(self) -> FlowResult | None:
        """Initialize the library profile, when manufacturer and model are set."""
        manufacturer: str | None = self.sensor_config.get(CONF_MANUFACTURER)
        model: str | None = self.sensor_config.get(CONF_MODEL)
        if not manufacturer or not model:
            return None

        try:
            model_info = ModelInfo(manufacturer, model)
            self.selected_profile = await get_power_profile(
                self.hass,
                {},
                self.source_entity,
                model_info,
            )
            if self.selected_profile and not self.strategy:
                self.strategy = self.selected_profile.calculation_strategy
        except ModelNotSupportedError:
            return self.async_abort(reason="model_not_supported")
        return None

    def build_menu(self) -> list[Step]:
        """Build the options menu."""
        menu = [Step.BASIC_OPTIONS]
        if self.selected_sensor_type == SensorType.VIRTUAL_POWER:
            if self.strategy and self.should_add_strategy_option_to_menu():
                strategy_step = STRATEGY_STEP_MAPPING[self.strategy]
                menu.append(strategy_step)
            if self.selected_profile:
                menu.append(Step.LIBRARY_OPTIONS)
            menu.append(Step.ADVANCED_OPTIONS)
        if self.selected_sensor_type == SensorType.DAILY_ENERGY:
            menu.append(Step.DAILY_ENERGY)
        if self.selected_sensor_type == SensorType.REAL_POWER:
            menu.append(Step.REAL_POWER)
        if self.selected_sensor_type == SensorType.GROUP:
            menu.extend(self.group_flow.build_group_menu())

        if self.sensor_config.get(CONF_CREATE_UTILITY_METERS):
            menu.append(Step.UTILITY_METER_OPTIONS)

        return menu

    def should_add_strategy_option_to_menu(self) -> bool:
        """Check whether the strategy option should be added to the menu."""
        if not self.strategy or self.strategy == CalculationStrategy.LUT:
            return False

        if self.selected_profile:
            if self.strategy == CalculationStrategy.FIXED and not self.selected_profile.needs_fixed_config:
                return False

            if self.strategy == CalculationStrategy.LINEAR and not self.selected_profile.needs_linear_config:
                return False

        return True

    async def async_step_global_configuration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        return await self.global_config_flow.async_step_global_configuration(user_input)

    async def async_step_basic_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        schema = fill_schema_defaults(
            self.build_basic_options_schema(),
            self.sensor_config,
        )
        return await self.async_handle_options_step(user_input, schema, Step.BASIC_OPTIONS)

    async def async_step_advanced_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        schema = fill_schema_defaults(
            SCHEMA_POWER_ADVANCED,
            self.sensor_config,
        )
        return await self.async_handle_options_step(user_input, schema, Step.ADVANCED_OPTIONS)

    async def async_step_utility_meter_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        schema = fill_schema_defaults(
            SCHEMA_UTILITY_METER_OPTIONS,
            self.sensor_config,
        )
        return await self.async_handle_options_step(user_input, schema, Step.UTILITY_METER_OPTIONS)

    async def async_step_daily_energy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the daily energy options flow."""
        schema = fill_schema_defaults(
            SCHEMA_DAILY_ENERGY_OPTIONS,
            self.sensor_config[CONF_DAILY_FIXED_ENERGY],
        )
        return await self.async_handle_options_step(user_input, schema, Step.DAILY_ENERGY)

    async def async_step_real_power(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the real power options flow."""
        schema = fill_schema_defaults(
            SCHEMA_REAL_POWER_OPTIONS,
            self.sensor_config,
        )
        return await self.async_handle_options_step(user_input, schema, Step.REAL_POWER)

    async def async_step_group_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        return await self.group_flow.async_step_group_custom(user_input)

    async def async_step_group_domain(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        return await self.group_flow.async_step_group_domain(user_input)

    async def async_step_group_subtract(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        return await self.group_flow.async_step_group_subtract(user_input)

    async def async_step_group_tracked_untracked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        return await self.group_flow.async_step_group_tracked_untracked(user_input)

    async def async_step_group_tracked_untracked_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        return await self.group_flow.async_step_group_tracked_untracked_manual(user_input)

    async def async_step_fixed(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        return await self.async_handle_strategy_options_step(user_input)

    async def async_step_linear(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        return await self.async_handle_strategy_options_step(user_input)

    async def async_step_wled(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        return await self.async_handle_strategy_options_step(user_input)

    async def async_step_multi_switch(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        return await self.async_handle_strategy_options_step(user_input)

    async def async_step_playbook(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        return await self.async_handle_strategy_options_step(user_input)

    async def async_step_library_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        self.is_library_flow = True
        self.selected_sub_profile = self.selected_profile.sub_profile  # type: ignore
        if user_input is not None:
            return await self.async_step_manufacturer()

        return self.async_show_form(
            step_id=Step.LIBRARY_OPTIONS,
            description_placeholders={
                "manufacturer": self.selected_profile.manufacturer,  # type: ignore
                "model": self.selected_profile.model,  # type: ignore
            },
            last_step=False,
        )

    async def async_handle_strategy_options_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the option processing for the selected strategy."""
        if not self.strategy:
            return self.async_abort(reason="no_strategy_selected")  # pragma: no cover

        step = STRATEGY_STEP_MAPPING.get(self.strategy, Step.FIXED)

        schema = self.create_strategy_schema()
        if self.selected_profile and self.selected_profile.device_type == DeviceType.SMART_SWITCH:
            schema = SCHEMA_POWER_SMART_SWITCH

        strategy_options = self.sensor_config.get(str(self.strategy)) or {}
        merged_options = {
            **self.sensor_config,
            **{k: v for k, v in strategy_options.items() if k not in self.sensor_config},
        }
        schema = fill_schema_defaults(schema, merged_options)
        return await self.async_handle_options_step(user_input, schema, step)

    async def async_handle_options_step(self, user_input: dict[str, Any] | None, schema: vol.Schema, step: Step) -> FlowResult:
        """
        Generic handler for all the option steps.
        processes user input against the select schema.
        And finally persist the changes on the config entry
        """
        errors: dict[str, str] | None = {}
        if user_input is not None:
            errors = await self.process_all_options(user_input, schema)
            if not errors:
                return self.persist_config_entry()
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    def persist_config_entry(self) -> FlowResult:
        """Persist changed options on the config entry."""
        data = (self.config_entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID and self.global_config) or self.sensor_config

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=data,
        )
        return self.async_create_entry(title="", data={})

    async def process_all_options(self, user_input: dict[str, Any], schema: vol.Schema) -> dict[str, str] | None:
        """
        Process the provided user input against the schema,
        and save the options data in current_config to save later on
        """

        assert self.cur_step is not None
        current_step: Step = Step(str(self.cur_step["step_id"]))
        is_strategy_step = current_step in STRATEGY_STEP_MAPPING.values()
        if self.strategy and is_strategy_step:
            if self.selected_profile and self.selected_profile.device_type == DeviceType.SMART_SWITCH:
                self._process_user_input(user_input, SCHEMA_POWER_SMART_SWITCH)
                user_input = {CONF_POWER: user_input.get(CONF_POWER, 0)}

            strategy_options = self.build_strategy_config(user_input or {})

            if self.strategy != CalculationStrategy.LUT:
                self.sensor_config.update({str(self.strategy): strategy_options})

            try:
                await self.validate_strategy_config()
                return None
            except SchemaFlowError as exc:
                return {"base": str(exc)}

        self._process_user_input(user_input, schema)

        if self.selected_sensor_type == SensorType.DAILY_ENERGY and current_step == Step.DAILY_ENERGY:
            self.sensor_config.update(self.build_daily_energy_config(user_input, SCHEMA_DAILY_ENERGY_OPTIONS))

        if CONF_ENTITY_ID in user_input:
            self.sensor_config[CONF_ENTITY_ID] = user_input[CONF_ENTITY_ID]

        return None

    def _process_user_input(
        self,
        user_input: dict[str, Any],
        schema: vol.Schema,
    ) -> None:
        """
        Process the provided user input against the schema.
        Update the current_config dictionary with the new options. We use that to save the data to config entry later on.
        """
        for key in schema.schema:
            if isinstance(key, vol.Marker):
                key = key.schema
            if key in user_input:
                self.sensor_config[key] = user_input.get(key)
            elif key in self.sensor_config:
                self.sensor_config.pop(key)

    def build_basic_options_schema(self) -> vol.Schema:
        """Build the basic options schema. depending on the selected sensor type."""
        if self.selected_sensor_type in [SensorType.REAL_POWER, SensorType.DAILY_ENERGY]:
            return SCHEMA_UTILITY_METER_TOGGLE

        if self.selected_sensor_type == SensorType.GROUP:
            return vol.Schema(
                {
                    **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
                    **SCHEMA_UTILITY_METER_TOGGLE.schema,
                },
            )

        schema = vol.Schema({})

        if self.source_entity_id != DUMMY_ENTITY_ID:
            schema = schema.extend(
                {vol.Optional(CONF_ENTITY_ID): self.create_source_entity_selector()},
            )

        if not (self.selected_profile and self.selected_profile.only_self_usage):
            schema = schema.extend(
                {vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float)},
            )

        return schema.extend(  # type: ignore
            {
                **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
                **SCHEMA_UTILITY_METER_TOGGLE.schema,
            },
        )
