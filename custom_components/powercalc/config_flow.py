"""Config flow for Powercalc integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
import logging
from typing import Any, cast
import uuid

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryBaseFlow,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_DEVICE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol

from .common import SourceEntity, create_source_entity
from .const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    DISCOVERY_POWER_PROFILES,
    DISCOVERY_SOURCE_ENTITY,
    DOMAIN,
    DUMMY_ENTITY_ID,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
    SensorType,
)
from .errors import ModelNotSupportedError, StrategyConfigurationError
from .flow_helper.common import FlowType, PowercalcFormStep, Step, fill_schema_defaults
from .flow_helper.flows.daily_energy import SCHEMA_DAILY_ENERGY_OPTIONS, DailyEnergyConfigFlow, DailyEnergyOptionsFlow, build_daily_energy_config
from .flow_helper.flows.global_configuration import (
    GlobalConfigurationConfigFlow,
    GlobalConfigurationOptionsFlow,
    get_global_powercalc_config,
)
from .flow_helper.flows.group import (
    GroupConfigFlow,
    GroupOptionsFlow,
)
from .flow_helper.flows.library import SCHEMA_POWER_SMART_SWITCH, LibraryConfigFlow, LibraryOptionsFlow
from .flow_helper.flows.real_power import RealPowerConfigFlow, RealPowerOptionsFlow
from .flow_helper.flows.virtual_power import (
    SCHEMA_POWER_ADVANCED,
    STRATEGY_STEP_MAPPING,
    VirtualPowerConfigFlow,
    VirtualPowerOptionsFlow,
)
from .flow_helper.schema import (
    SCHEMA_ENERGY_SENSOR_TOGGLE,
    SCHEMA_SENSOR_ENERGY_OPTIONS,
    SCHEMA_UTILITY_METER_OPTIONS,
    SCHEMA_UTILITY_METER_TOGGLE,
)
from .power_profile.factory import get_power_profile
from .power_profile.library import ModelInfo
from .power_profile.power_profile import SUPPORTED_DOMAINS, DeviceType, DiscoveryBy, PowerProfile
from .strategy.factory import PowerCalculatorStrategyFactory

_LOGGER = logging.getLogger(__name__)

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

FLOW_HANDLERS: dict[FlowType, dict] = {
    FlowType.GROUP: {
        "config": GroupConfigFlow,
        "options": GroupOptionsFlow,
    },
    FlowType.DAILY_ENERGY: {
        "config": DailyEnergyConfigFlow,
        "options": DailyEnergyOptionsFlow,
    },
    FlowType.LIBRARY: {
        "config": LibraryConfigFlow,
        "options": LibraryOptionsFlow,
    },
    FlowType.VIRTUAL_POWER: {
        "config": VirtualPowerConfigFlow,
        "options": VirtualPowerOptionsFlow,
    },
    FlowType.GLOBAL_CONFIGURATION: {
        "config": GlobalConfigurationConfigFlow,
        "options": GlobalConfigurationOptionsFlow,
    },
    FlowType.REAL_POWER: {
        "config": RealPowerConfigFlow,
        "options": RealPowerOptionsFlow,
    },
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

        # Initialize flow handlers
        flow_key = "options" if self.is_options_flow else "config"
        self.flow_handlers = {
            FlowType.GLOBAL_CONFIGURATION: FLOW_HANDLERS[FlowType.GLOBAL_CONFIGURATION][flow_key](self),
            FlowType.LIBRARY: FLOW_HANDLERS[FlowType.LIBRARY][flow_key](self),
            FlowType.VIRTUAL_POWER: FLOW_HANDLERS[FlowType.VIRTUAL_POWER][flow_key](self),
            FlowType.GROUP: FLOW_HANDLERS[FlowType.GROUP][flow_key](self),
            FlowType.DAILY_ENERGY: FLOW_HANDLERS[FlowType.DAILY_ENERGY][flow_key](self),
            FlowType.REAL_POWER: FLOW_HANDLERS[FlowType.REAL_POWER][flow_key](self),
        }

        for step in Step:
            step_method = f"async_step_{step}"
            if hasattr(self, step_method):
                continue
            setattr(self, step_method, self._async_step(step))

        super().__init__()

    @abstractmethod
    @callback
    def persist_config_entry(self) -> FlowResult:
        pass  # pragma: no cover

    def _async_step(self, step: Step) -> Callable:
        """Generate a step handler."""

        async def _async_step(
            user_input: dict[str, Any] | None = None,
        ) -> ConfigFlowResult:
            """Handle a config flow step."""
            return await self.async_step(step, user_input)

        return _async_step

    async def async_step(self, step: Step, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle a config flow step by delegating to specific handler."""
        step_method = f"async_step_{step}"
        for handler in self.flow_handlers.values():
            if hasattr(handler, step_method):
                return await getattr(handler, step_method)(user_input)  # type:ignore
        raise SchemaFlowError("No handler defined")  # pragma: nocover

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
            return await self.flow_handlers[FlowType.VIRTUAL_POWER].async_step_power_advanced()  # type:ignore
        if not skip_utility_meter_options and self.sensor_config.get(CONF_CREATE_UTILITY_METERS):
            return await self.async_step_utility_meter_options()
        return self.persist_config_entry()

    async def _show_form(self, form_step: PowercalcFormStep, error: SchemaFlowError | None = None) -> FlowResult:
        # Show form for next step
        last_step = None
        if not callable(form_step.next_step):
            last_step = form_step.next_step is None

        schema = await self._get_schema(form_step)
        # noinspection PyTypeChecker
        form_data = form_step.form_data
        if form_data is None:
            form_data = {**self.sensor_config, **get_global_powercalc_config(self)}
        return self.async_show_form(
            step_id=form_step.step,
            data_schema=fill_schema_defaults(schema, form_data),
            errors={"base": str(error)} if error else {},
            last_step=last_step,
            **(form_step.form_kwarg or {}),
        )

    async def _get_schema(self, form_step: PowercalcFormStep) -> vol.Schema:
        if isinstance(form_step.schema, vol.Schema):
            return form_step.schema
        return await form_step.schema()

    async def async_step_utility_meter_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for utility meter options."""
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.UTILITY_METER_OPTIONS,
                schema=SCHEMA_UTILITY_METER_OPTIONS,
            ),
            user_input,
        )

    async def async_step_energy_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for utility meter options."""
        return await self.handle_form_step(
            PowercalcFormStep(
                step=Step.ENERGY_OPTIONS,
                schema=SCHEMA_SENSOR_ENERGY_OPTIONS,
                continue_utility_meter_options_step=not self.is_options_flow,
            ),
            user_input,
        )


class PowercalcConfigFlow(PowercalcCommonFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PowerCalc."""

    VERSION = 6

    def __init__(self) -> None:
        """Initialize options flow."""
        self.discovered_profiles: dict[str, PowerProfile] = {}
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
            del discovery_info[DISCOVERY_POWER_PROFILES]

        self.sensor_config = discovery_info.copy()

        self.context["title_placeholders"] = {
            "name": self.name or "",
            "manufacturer": str(self.sensor_config.get(CONF_MANUFACTURER)),
            "model": str(self.sensor_config.get(CONF_MODEL)),
        }

        self.skip_advanced_step = True  # We don't want to ask advanced options when discovered
        self.is_library_flow = True

        if discovery_info.get(CONF_MODE) == CalculationStrategy.WLED:
            return await self.flow_handlers[FlowType.VIRTUAL_POWER].async_step_wled()  # type:ignore

        if len(power_profiles) > 1:
            return cast(ConfigFlowResult, await self.flow_handlers[FlowType.LIBRARY].async_step_library_multi_profile())

        self.selected_profile = power_profiles[0]
        return cast(ConfigFlowResult, await self.flow_handlers[FlowType.LIBRARY].async_step_library())

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Start flow when initialized by the user."""

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

    async def async_step_menu_library(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the Virtual power (library) step.
        We forward to the virtual_power step, but without the strategy selector displayed.
        """
        self.is_library_flow = True
        return await self.flow_handlers[FlowType.VIRTUAL_POWER].async_step_virtual_power(user_input)  # type:ignore

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
        self.sensor_config = dict(config_entry.data)
        self.strategy = self.sensor_config.get(CONF_MODE)

    @callback
    def abort_if_unique_id_configured(self) -> None:
        """Return if unique_id is already configured."""
        # pragma: nocover

    async def async_set_unique_id(self, unique_id: str | None, raise_on_progress: bool = True) -> None:
        """Set the unique ID of the flow."""
        # pragma: nocover

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle options flow."""
        self.selected_sensor_type = self.sensor_config.get(CONF_SENSOR_TYPE) or SensorType.VIRTUAL_POWER
        self.source_entity_id = self.sensor_config.get(CONF_ENTITY_ID)

        if self.config_entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
            self.global_config = get_global_powercalc_config(self)
            return self.async_show_menu(step_id=Step.INIT, menu_options=self.flow_handlers[FlowType.GLOBAL_CONFIGURATION].build_global_config_menu())

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
            menu.extend([Step.REAL_POWER, Step.ENERGY_OPTIONS])
        if self.selected_sensor_type == SensorType.GROUP:
            menu.extend(self.flow_handlers[FlowType.GROUP].build_group_menu())

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

            strategy_options = await self.flow_handlers[FlowType.VIRTUAL_POWER].build_strategy_config(user_input or {})

            if self.strategy != CalculationStrategy.LUT:
                self.sensor_config.update({str(self.strategy): strategy_options})

            try:
                await self.validate_strategy_config()
                return None
            except SchemaFlowError as exc:
                return {"base": str(exc)}

        self._process_user_input(user_input, schema)

        if self.selected_sensor_type == SensorType.DAILY_ENERGY and current_step == Step.DAILY_ENERGY:
            self.sensor_config.update(build_daily_energy_config(user_input, SCHEMA_DAILY_ENERGY_OPTIONS))

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
