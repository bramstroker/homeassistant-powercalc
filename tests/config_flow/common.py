from collections.abc import Mapping
import json
from typing import Any

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowManager, FlowResult, section
import pytest
import voluptuous as vol

from custom_components.powercalc import DiscoveryManager
from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.config_flow import (
    DOMAIN,
    Step,
)
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_FIXED_VALUE,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    DISCOVERY_POWER_PROFILES,
    DISCOVERY_SOURCE_ENTITY,
    ENERGY_INTEGRATION_METHOD_LEFT,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.flow_helper.flows.global_configuration import SCHEMA_GLOBAL_CONFIGURATION
from custom_components.powercalc.flow_helper.flows.group import create_schema_group_custom
from custom_components.powercalc.flow_helper.flows.library import CONF_CONFIRM_AUTODISCOVERED_MODEL
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.power_profile import PowerProfile

DEFAULT_ENTITY_ID = "light.test"
DEFAULT_UNIQUE_ID = "7c009ef6829f"


def _schema_keys(schema: vol.Schema) -> set[str]:
    """Return the plain field keys of a (flat) voluptuous schema."""
    return {key.schema if isinstance(key, vol.Marker) else key for key in schema.schema}


def section_schema(data_schema: vol.Schema, section_key: str) -> vol.Schema:
    """Return the inner schema of a collapsible `section` within a form schema."""
    for key, val in data_schema.schema.items():
        base_key = key.schema if isinstance(key, vol.Marker) else key
        if base_key == section_key:
            return val.schema
    raise KeyError(section_key)


def build_section_input(flat: dict[str, Any], sections: dict[str, set[str]]) -> dict[str, Any]:
    """Convert a flat user input into the nested section structure a form expects.

    ``sections`` maps each section key to the field keys that live inside it. Fields not
    belonging to any section stay at the top level. All section keys are always present
    (possibly empty), matching the required sections in the form schema.
    """
    result: dict[str, Any] = {section_key: {} for section_key in sections}
    for key, value in flat.items():
        for section_key, field_keys in sections.items():
            if key in field_keys:
                result[section_key][key] = value
                break
        else:
            result[key] = value
    return result


def _schema_sections(schema: vol.Schema) -> dict[str, set[str]]:
    """Map each collapsible section in a form schema to the field keys it contains."""
    sections: dict[str, set[str]] = {}
    for key, val in schema.schema.items():
        base_key = key.schema if isinstance(key, vol.Marker) else key
        if isinstance(val, section):
            sections[base_key] = _schema_keys(val.schema)
    return sections


def _sections_for_step(hass: HomeAssistant, step: Step) -> dict[str, set[str]] | None:
    """Return the section layout (section key -> field keys) for a form step, if it has any.

    Steps whose forms group fields into collapsible sections are listed here so submissions
    can be flattened automatically. The group-custom layout uses the config-flow schema, whose
    section field keys are a superset of the options-flow schema, so it covers both flows.
    """
    if step == Step.GLOBAL_CONFIGURATION:
        return _schema_sections(SCHEMA_GLOBAL_CONFIGURATION)
    if step == Step.GROUP_CUSTOM:
        return _schema_sections(create_schema_group_custom(hass, is_option_flow=False))
    return None


async def submit_form_step(
    hass: HomeAssistant,
    result: FlowResult,
    user_input: dict[str, Any] | None = None,
) -> FlowResult:
    """Submit flat user input to the current config-flow step.

    The step is read from ``result``; if it groups fields into collapsible sections the flat
    input is distributed into them automatically, so tests never nest the input themselves.
    """
    return await _submit_step(hass.config_entries.flow, hass, result, user_input)


async def submit_options_step(
    hass: HomeAssistant,
    result: FlowResult,
    user_input: dict[str, Any] | None = None,
) -> FlowResult:
    """Options-flow counterpart of :func:`submit_form_step`."""
    return await _submit_step(hass.config_entries.options, hass, result, user_input)


async def _submit_step(
    manager: FlowManager,
    hass: HomeAssistant,
    result: FlowResult,
    user_input: dict[str, Any] | None,
) -> FlowResult:
    sections = _sections_for_step(hass, Step(result["step_id"]))
    if sections is not None:
        user_input = build_section_input(user_input or {}, sections)
    return await manager.async_configure(result["flow_id"], user_input or {})


async def select_menu_item(
    hass: HomeAssistant,
    menu_item: Step,
    next_step_id: Step | None = None,
) -> FlowResult:
    """Select a sensor type from the menu"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": menu_item},
    )

    if menu_item == Step.MENU_GROUP:
        assert result["type"] == data_entry_flow.FlowResultType.MENU
    else:
        assert result["type"] == data_entry_flow.FlowResultType.FORM

    if next_step_id:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"next_step_id": next_step_id},
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == next_step_id

    return result


async def select_manufacturer_and_model(
    hass: HomeAssistant,
    prev_result: FlowResult,
    manufacturer: str,
    model: str,
) -> FlowResult:
    assert prev_result["step_id"] == Step.MANUFACTURER
    result = await hass.config_entries.flow.async_configure(
        prev_result["flow_id"],
        {CONF_MANUFACTURER: manufacturer},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL

    return await hass.config_entries.flow.async_configure(
        prev_result["flow_id"],
        {CONF_MODEL: model},
    )


async def confirm_auto_discovered_model(
    hass: HomeAssistant,
    prev_result: FlowResult,
    confirmed: bool = True,
) -> FlowResult:
    assert prev_result["step_id"] == Step.LIBRARY
    return await hass.config_entries.flow.async_configure(
        prev_result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: confirmed},
    )


async def initialize_options_flow(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    selected_menu_item: Step,
) -> FlowResult:
    """Initialize the options flow for a given config entry."""
    if entry.state == config_entries.ConfigEntryState.NOT_LOADED:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    assert selected_menu_item in result["menu_options"]

    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": selected_menu_item},
    )


async def handle_options_flow_update(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    selected_menu_item: Step,
    user_input: dict[str, Any],
) -> FlowResult:
    """Open the options flow, select a menu item, and handle (flat) user input."""
    result = await initialize_options_flow(hass, entry, selected_menu_item)
    result = await submit_options_step(hass, result, user_input)
    await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    return result


async def initialize_discovery_flow(
    hass: HomeAssistant,
    source_entity: SourceEntity,
    power_profiles: PowerProfile | list[PowerProfile | None] | None = None,
    confirm_autodiscovered_model: bool = False,
) -> FlowResult:
    discovery_manager: DiscoveryManager = DiscoveryManager(hass, {})
    if not power_profiles:
        power_profiles = [
            await get_power_profile(
                hass,
                {},
                source_entity,
                await discovery_manager.extract_model_info_from_device_info(source_entity.entity_entry),
            ),
        ]

    discovery_data = {
        CONF_NAME: "test",
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        DISCOVERY_SOURCE_ENTITY: source_entity,
    }

    if isinstance(power_profiles, PowerProfile):
        discovery_data.update(
            {
                CONF_MANUFACTURER: power_profiles.manufacturer,
                CONF_MODEL: power_profiles.model,
            },
        )
        power_profiles = [power_profiles]

    discovery_data[DISCOVERY_POWER_PROFILES] = power_profiles

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data=discovery_data,
    )
    if not confirm_autodiscovered_model:
        return result

    return await confirm_auto_discovered_model(hass, result)


async def goto_virtual_power_strategy_step(
    hass: HomeAssistant,
    strategy: CalculationStrategy,
    user_input: dict[str, Any] | None = None,
) -> FlowResult:
    """
    - Select the virtual power sensor type
    - Select the given calculation strategy and put in default configuration options
    """

    if user_input is None:
        user_input = {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MODE: strategy,
        }
    elif CONF_MODE not in user_input:
        user_input[CONF_MODE] = strategy

    result = await select_menu_item(hass, Step.VIRTUAL_POWER)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    if len(result.get("errors")):
        pytest.fail(reason=json.dumps(result["errors"]))

    assert result["type"] == data_entry_flow.FlowResultType.FORM

    # Lut has alternate flows depending on auto discovery, don't need to assert here
    if strategy != CalculationStrategy.LUT:
        assert result["step_id"] == strategy

    return result


async def process_config_flow(
    hass: HomeAssistant,
    result: FlowResult | None,
    user_inputs: dict[Step, dict],
) -> FlowResult | None:
    """Process a configuration flow with multiple steps and user inputs."""
    if not result:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

    for step, user_input in user_inputs.items():
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == step, f"Expected step {step}, got {result['step_id']}"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )
    return result


async def set_virtual_power_configuration(
    hass: HomeAssistant,
    previous_result: FlowResult,
    basic_options: dict[str, Any] | None = None,
    advanced_options: dict[str, Any] | None = None,
    group_options: dict[str, Any] | None = None,
) -> FlowResult:
    result = await hass.config_entries.flow.async_configure(
        previous_result["flow_id"],
        basic_options or {},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    if result["step_id"] == Step.ASSIGN_GROUPS:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            group_options or {},
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.POWER_ADVANCED
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        advanced_options or {},
    )


def assert_default_virtual_power_entry_data(
    strategy: CalculationStrategy,
    config_entry_data: Mapping[str, Any],
    expected_strategy_options: dict,
) -> None:
    assert (
        config_entry_data
        == {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: strategy,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_NAME: "test",
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_LEFT,
            CONF_ENERGY_FILTER_OUTLIER_ENABLED: False,
        }
        | expected_strategy_options
    )


def fixed_value_choice(choice: str, value: object) -> dict[str, object]:
    return {CONF_FIXED_VALUE: {"active_choice": choice, choice: value}}
