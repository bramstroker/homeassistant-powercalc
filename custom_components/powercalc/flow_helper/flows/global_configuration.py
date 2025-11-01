from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import CONF_SENSORS, UnitOfTime
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES,
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_GROUP_UPDATE_INTERVAL,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_UTILITY_METER_OFFSET,
    DOMAIN,
    DOMAIN_CONFIG,
    ENTITY_CATEGORIES,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    DeviceType,
)
from custom_components.powercalc.flow_helper.common import Step, fill_schema_defaults
from custom_components.powercalc.flow_helper.schema import SCHEMA_ENERGY_OPTIONS, SCHEMA_UTILITY_METER_OPTIONS, SCHEMA_UTILITY_METER_TOGGLE

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcCommonFlow, PowercalcConfigFlow, PowercalcOptionsFlow

SCHEMA_GLOBAL_CONFIGURATION = vol.Schema(
    {
        vol.Optional(CONF_POWER_SENSOR_NAMING): selector.TextSelector(),
        vol.Optional(CONF_POWER_SENSOR_FRIENDLY_NAMING): selector.TextSelector(),
        vol.Optional(CONF_POWER_SENSOR_CATEGORY): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(filter(lambda item: item is not None, ENTITY_CATEGORIES)),  # type: ignore
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        vol.Optional(CONF_POWER_SENSOR_PRECISION): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=6, mode=selector.NumberSelectorMode.BOX, step=1),
        ),
        vol.Optional(CONF_GROUP_UPDATE_INTERVAL): selector.NumberSelector(
            selector.NumberSelectorConfig(unit_of_measurement=UnitOfTime.SECONDS, mode=selector.NumberSelectorMode.BOX),
        ),
        vol.Optional(CONF_FORCE_UPDATE_FREQUENCY): selector.NumberSelector(
            selector.NumberSelectorConfig(unit_of_measurement=UnitOfTime.SECONDS, mode=selector.NumberSelectorMode.BOX),
        ),
        vol.Optional(CONF_IGNORE_UNAVAILABLE_STATE, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_INCLUDE_NON_POWERCALC_SENSORS, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_DISABLE_EXTENDED_ATTRIBUTES, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_DISABLE_LIBRARY_DOWNLOAD, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_CREATE_ENERGY_SENSORS, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[cls.value for cls in DeviceType],
                mode=selector.SelectSelectorMode.DROPDOWN,
                multiple=True,
            ),
        ),
        vol.Optional(CONF_DISCOVERY_EXCLUDE_SELF_USAGE, default=False): selector.BooleanSelector(),
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_GLOBAL_CONFIGURATION_ENERGY_SENSOR = vol.Schema(
    {
        vol.Optional(CONF_ENERGY_SENSOR_NAMING): selector.TextSelector(),
        vol.Optional(CONF_ENERGY_SENSOR_FRIENDLY_NAMING): selector.TextSelector(),
        vol.Optional(CONF_ENERGY_SENSOR_CATEGORY): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(filter(lambda item: item is not None, ENTITY_CATEGORIES)),  # type: ignore
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        **SCHEMA_ENERGY_OPTIONS.schema,
        vol.Optional(CONF_ENERGY_SENSOR_PRECISION): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=6, mode=selector.NumberSelectorMode.BOX, step=1),
        ),
    },
)


def get_global_powercalc_config(flow) -> ConfigType:
    """Get the global powercalc config."""
    if flow.global_config:
        return flow.global_config
    powercalc = flow.hass.data.get(DOMAIN) or {}
    global_config = dict.copy(powercalc.get(DOMAIN_CONFIG) or {})
    force_update_frequency = global_config.get(CONF_FORCE_UPDATE_FREQUENCY)
    if isinstance(force_update_frequency, timedelta):
        global_config[CONF_FORCE_UPDATE_FREQUENCY] = force_update_frequency.total_seconds()
    utility_meter_offset = global_config.get(CONF_UTILITY_METER_OFFSET)
    if isinstance(utility_meter_offset, timedelta):
        global_config[CONF_UTILITY_METER_OFFSET] = utility_meter_offset.days
    if CONF_SENSORS in global_config:
        global_config.pop(CONF_SENSORS)
    flow.global_config = global_config
    return global_config


class GlobalConfigurationFlow:
    def __init__(self, flow: PowercalcCommonFlow) -> None:
        self.flow = flow

    async def async_step_global_configuration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        get_global_powercalc_config(self.flow)
        await self.flow.async_set_unique_id(ENTRY_GLOBAL_CONFIG_UNIQUE_ID)
        self.flow.abort_if_unique_id_configured()

        if user_input is not None:
            self.flow.global_config.update(user_input)
            return await self.flow.async_step_global_configuration_energy()

        return self.flow.async_show_form(
            step_id=Step.GLOBAL_CONFIGURATION,
            data_schema=fill_schema_defaults(
                SCHEMA_GLOBAL_CONFIGURATION,
                self.flow.global_config,
            ),
            errors={},
        )

    async def async_step_global_configuration_energy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""

        if user_input is not None:
            self.flow.global_config.update(user_input)
            if self.flow.is_options_flow:
                return self.flow.persist_config_entry()

        if not bool(self.flow.global_config.get(CONF_CREATE_ENERGY_SENSORS)) or user_input is not None:
            return await self.flow.async_step_global_configuration_utility_meter()

        return self.flow.async_show_form(
            step_id=Step.GLOBAL_CONFIGURATION_ENERGY,
            data_schema=fill_schema_defaults(
                SCHEMA_GLOBAL_CONFIGURATION_ENERGY_SENSOR,
                self.flow.global_config,
            ),
            errors={},
        )

    async def async_step_global_configuration_utility_meter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""

        if user_input is not None:
            self.flow.global_config.update(user_input)
            if self.flow.is_options_flow:
                return self.flow.persist_config_entry()

        if not bool(self.flow.global_config.get(CONF_CREATE_UTILITY_METERS)) or user_input is not None:
            return self.flow.async_create_entry(
                title="Global Configuration",
                data=self.flow.global_config,
            )

        return self.flow.async_show_form(
            step_id=Step.GLOBAL_CONFIGURATION_UTILITY_METER,
            data_schema=fill_schema_defaults(
                SCHEMA_UTILITY_METER_OPTIONS,
                self.flow.global_config,
            ),
            errors={},
        )


class GlobalConfigurationConfigFlow(GlobalConfigurationFlow):
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        super().__init__(flow)
        self.flow = flow

    async def async_step_global_configuration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""
        get_global_powercalc_config(self.flow)
        await self.flow.async_set_unique_id(ENTRY_GLOBAL_CONFIG_UNIQUE_ID)
        self.flow.abort_if_unique_id_configured()

        if user_input is not None:
            self.flow.global_config.update(user_input)
            return await self.flow.async_step_global_configuration_energy()

        return self.flow.async_show_form(
            step_id=Step.GLOBAL_CONFIGURATION,
            data_schema=fill_schema_defaults(
                SCHEMA_GLOBAL_CONFIGURATION,
                self.flow.global_config,
            ),
            errors={},
        )


class GlobalConfigurationOptionsFlow(GlobalConfigurationFlow):
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        super().__init__(flow)
        self.flow = flow

    def build_global_config_menu(self) -> dict[Step, str]:
        """Build menu for global configuration"""
        menu = {
            Step.GLOBAL_CONFIGURATION: "Basic options",
        }
        if self.flow.global_config.get(CONF_CREATE_ENERGY_SENSORS):
            menu[Step.GLOBAL_CONFIGURATION_ENERGY] = "Energy options"
        if self.flow.global_config.get(CONF_CREATE_UTILITY_METERS):
            menu[Step.GLOBAL_CONFIGURATION_UTILITY_METER] = "Utility meter options"
        return menu

    async def async_step_global_configuration(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the global configuration step."""

        if user_input is not None:
            self.flow.global_config.update(user_input)
            return self.flow.persist_config_entry()

        return self.flow.async_show_form(
            step_id=Step.GLOBAL_CONFIGURATION,
            data_schema=fill_schema_defaults(
                SCHEMA_GLOBAL_CONFIGURATION,
                self.flow.global_config,
            ),
            errors={},
        )
