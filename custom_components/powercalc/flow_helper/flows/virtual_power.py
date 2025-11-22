from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_ATTRIBUTE, CONF_ENTITIES, CONF_ENTITY_ID, CONF_ID, CONF_NAME, CONF_PATH, Platform
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
import voluptuous as vol

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import (
    CONF_AUTOSTART,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_GAMMA_CURVE,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_POWER_TEMPLATE,
    CONF_REPEAT,
    CONF_STANDBY_POWER,
    CONF_STATE_TRIGGER,
    CONF_STATES_POWER,
    CONF_UNAVAILABLE_POWER,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import FlowType, PowercalcFormStep, Step, fill_schema_defaults
from custom_components.powercalc.flow_helper.flows.global_configuration import get_global_powercalc_config
from custom_components.powercalc.flow_helper.flows.library import SCHEMA_POWER_OPTIONS_LIBRARY, SCHEMA_POWER_SMART_SWITCH
from custom_components.powercalc.flow_helper.schema import (
    SCHEMA_ENERGY_SENSOR_TOGGLE,
    SCHEMA_SENSOR_ENERGY_OPTIONS,
    SCHEMA_UTILITY_METER_TOGGLE,
)
from custom_components.powercalc.power_profile.power_profile import DeviceType
from custom_components.powercalc.strategy.wled import CONFIG_SCHEMA as SCHEMA_POWER_WLED

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcCommonFlow, PowercalcConfigFlow, PowercalcOptionsFlow

SCHEMA_POWER_ADVANCED = vol.Schema(
    {
        vol.Optional(CONF_CALCULATION_ENABLED_CONDITION): selector.TemplateSelector(),
        vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE): selector.BooleanSelector(),
        vol.Optional(CONF_UNAVAILABLE_POWER): vol.Coerce(float),
        vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
        vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY): selector.BooleanSelector(),
    },
)

SCHEMA_POWER_BASE = vol.Schema(
    {
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

SCHEMA_POWER_FIXED = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_STATES_POWER): selector.ObjectSelector(),
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

STRATEGY_SCHEMAS: dict[CalculationStrategy, vol.Schema] = {
    CalculationStrategy.FIXED: SCHEMA_POWER_FIXED,
    CalculationStrategy.WLED: SCHEMA_POWER_WLED,
}

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

STRATEGY_STEP_MAPPING: dict[CalculationStrategy, Step] = {
    CalculationStrategy.FIXED: Step.FIXED,
    CalculationStrategy.LINEAR: Step.LINEAR,
    CalculationStrategy.MULTI_SWITCH: Step.MULTI_SWITCH,
    CalculationStrategy.PLAYBOOK: Step.PLAYBOOK,
    CalculationStrategy.WLED: Step.WLED,
}


class VirtualPowerFlow:
    def __init__(self, flow: PowercalcCommonFlow) -> None:
        self.flow = flow

    async def create_strategy_schema(self) -> vol.Schema:
        """Get the config schema for a given power calculation strategy."""
        if not self.flow.strategy:
            raise ValueError("No strategy selected")  # pragma: no cover

        create_schema_func = f"create_schema_{self.flow.strategy.lower()}"
        if hasattr(self, create_schema_func):
            return await getattr(self, create_schema_func)()  # type: ignore

        return STRATEGY_SCHEMAS[self.flow.strategy]

    async def create_schema_linear(self) -> vol.Schema:
        """Create the config schema for linear strategy."""
        return SCHEMA_POWER_LINEAR.extend(  # type: ignore
            {
                vol.Optional(CONF_ATTRIBUTE): selector.AttributeSelector(
                    selector.AttributeSelectorConfig(
                        entity_id=self.flow.source_entity_id,  # type: ignore
                        hide_attributes=[],
                    ),
                ),
            },
        )

    async def create_schema_multi_switch(self) -> vol.Schema:
        """Create the config schema for multi switch strategy."""

        switch_domains = [str(Platform.SWITCH), str(Platform.LIGHT), str(Platform.COVER)]
        if self.flow.source_entity and self.flow.source_entity.device_entry:
            entity_selector = self.flow.create_device_entity_selector(switch_domains, multiple=True)
        else:
            entity_selector = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=switch_domains,
                    multiple=True,
                ),
            )

        default_entities = entity_selector.config.get("include_entities", [])
        schema = vol.Schema({vol.Optional(CONF_ENTITIES, default=default_entities): entity_selector})

        if not self.flow.is_library_flow:
            schema = schema.extend(SCHEMA_POWER_MULTI_SWITCH_MANUAL.schema)

        return schema

    async def create_schema_playbook(self) -> vol.Schema:
        """Create the config schema for playbook strategy."""
        base_path = Path(self.flow.hass.config.path("powercalc/playbooks"))
        playbook_files = [str(p.relative_to(base_path)) for p in base_path.rglob("*") if p.is_file()]

        return vol.Schema(
            {
                vol.Optional(CONF_PLAYBOOKS): selector.ObjectSelector(
                    {
                        "multiple": True,
                        "description_field": CONF_PATH,
                        "label_field": CONF_ID,
                        "fields": {
                            CONF_ID: {
                                "required": True,
                                "selector": {"text": None},
                            },
                            CONF_PATH: {
                                "required": True,
                                "selector": {"select": {"options": playbook_files, "mode": "dropdown", "custom_value": True}},
                            },
                        },
                    },
                ),
                vol.Optional(CONF_REPEAT): selector.BooleanSelector(),
                vol.Optional(CONF_AUTOSTART): selector.TextSelector(),
                vol.Optional(CONF_STATE_TRIGGER): selector.ObjectSelector(),
            },
        )

    async def handle_strategy_step(
        self,
        strategy: CalculationStrategy,
        user_input: dict[str, Any] | None = None,
        validate: Callable[[dict[str, Any]], None] | None = None,
    ) -> FlowResult:
        self.flow.strategy = strategy

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            if validate:
                validate(user_input)
            await self.flow.validate_strategy_config({strategy: user_input})
            return {strategy: user_input}

        schema = await self.create_strategy_schema()

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=STRATEGY_STEP_MAPPING[strategy],
                schema=schema,
                next_step=Step.ASSIGN_GROUPS,
                validate_user_input=_validate,
            ),
            user_input,
        )

    async def async_step_power_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for advanced options."""

        if self.flow.is_options_flow:
            return self.flow.persist_config_entry()  # pragma: no cover

        if user_input is not None or self.flow.skip_advanced_step:
            self.flow.sensor_config.update(user_input or {})
            if self.flow.sensor_config.get(CONF_CREATE_UTILITY_METERS):
                return await self.flow.async_step_utility_meter_options()
            return self.flow.persist_config_entry()

        schema = SCHEMA_POWER_ADVANCED
        if self.flow.sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
            schema = schema.extend(SCHEMA_SENSOR_ENERGY_OPTIONS.schema)

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.POWER_ADVANCED,
                schema=fill_schema_defaults(
                    schema,
                    get_global_powercalc_config(self.flow),
                ),
            ),
        )


class VirtualPowerConfigFlow(VirtualPowerFlow):
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcConfigFlow = flow

    def create_schema_virtual_power(
        self,
    ) -> vol.Schema:
        """Create the config schema for virtual power sensor."""
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTITY_ID): self.flow.create_source_entity_selector(),
            },
        ).extend(SCHEMA_POWER_BASE.schema)
        if not self.flow.is_library_flow:
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
            get_global_powercalc_config(self.flow),
        )
        return schema.extend(power_options.schema)  # type: ignore

    async def async_step_virtual_power(self, user_input: dict[str, Any] | None = None) -> FlowResult:
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
                self.flow.source_entity_id = str(entity_id or DUMMY_ENTITY_ID)
                self.flow.source_entity = await create_source_entity(
                    self.flow.source_entity_id,
                    self.flow.hass,
                )

                self.flow.name = user_input.get(CONF_NAME) or self.flow.source_entity.name
                self.flow.selected_sensor_type = SensorType.VIRTUAL_POWER
                self.flow.sensor_config.update(user_input)

                return await self.forward_to_strategy_step(selected_strategy)

        return self.flow.async_show_form(  # type: ignore
            step_id=Step.VIRTUAL_POWER,
            data_schema=self.create_schema_virtual_power(),
            errors=errors,
            last_step=False,
        )

    async def async_step_fixed(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for fixed sensor."""
        return await self.handle_strategy_step(CalculationStrategy.FIXED, user_input)

    async def async_step_linear(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for fixed sensor."""
        return await self.handle_strategy_step(CalculationStrategy.LINEAR, user_input)

    async def async_step_multi_switch(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for multi switch strategy."""
        return await self.handle_strategy_step(CalculationStrategy.MULTI_SWITCH, user_input)

    async def async_step_wled(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for WLED sensor."""
        return await self.handle_strategy_step(CalculationStrategy.WLED, user_input)

    async def async_step_playbook(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for playbook sensor."""

        def _validate(user_input: dict[str, Any]) -> None:
            if user_input.get(CONF_PLAYBOOKS) is None or len(user_input.get(CONF_PLAYBOOKS)) == 0:  # type: ignore
                raise SchemaFlowError("playbook_mandatory")

        return await self.handle_strategy_step(CalculationStrategy.PLAYBOOK, user_input, _validate)

    async def forward_to_strategy_step(self, strategy: CalculationStrategy) -> FlowResult:
        """Forward to the next step based on the selected strategy."""
        step = STRATEGY_STEP_MAPPING.get(strategy)
        if step is None:
            return await self.flow.flow_handlers[FlowType.LIBRARY].async_step_library()  # type:ignore
        method = getattr(self.flow, f"async_step_{step}")
        return await method()  # type: ignore


class VirtualPowerOptionsFlow(VirtualPowerFlow):
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcOptionsFlow = flow

    async def build_strategy_config(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the config dict needed for the configured strategy."""
        strategy_schema = await self.create_strategy_schema()
        strategy_options: dict[str, Any] = {}
        for key in strategy_schema.schema:
            if user_input.get(key) is None:
                continue
            strategy_options[str(key)] = user_input.get(key)
        return strategy_options

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

    async def async_handle_strategy_options_step(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the option processing for the selected strategy."""
        step = STRATEGY_STEP_MAPPING.get(self.flow.strategy or CalculationStrategy.FIXED, Step.FIXED)

        schema = await self.create_strategy_schema()
        if self.flow.selected_profile and self.flow.selected_profile.device_type == DeviceType.SMART_SWITCH:
            schema = SCHEMA_POWER_SMART_SWITCH

        strategy_options = self.flow.sensor_config.get(str(self.flow.strategy)) or {}
        merged_options = {
            **self.flow.sensor_config,
            **{k: v for k, v in strategy_options.items() if k not in self.flow.sensor_config},
        }
        schema = fill_schema_defaults(schema, merged_options)
        return await self.flow.async_handle_options_step(user_input, schema, step)
