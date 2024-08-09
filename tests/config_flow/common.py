import json
from collections.abc import Mapping
from typing import Any

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.typing import ConfigType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import DiscoveryManager
from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.config_flow import (
    CONF_CONFIRM_AUTODISCOVERED_MODEL,
    DOMAIN,
    Steps,
)
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    DISCOVERY_POWER_PROFILE,
    DISCOVERY_SOURCE_ENTITY,
    ENERGY_INTEGRATION_METHOD_LEFT,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.power_profile import PowerProfile

DEFAULT_ENTITY_ID = "light.test"
DEFAULT_UNIQUE_ID = "7c009ef6829f"


async def select_menu_item(
    hass: HomeAssistant,
    menu_item: Steps,
    next_step_id: Steps | None = None,
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

    if menu_item == Steps.MENU_GROUP:
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


async def initialize_options_flow(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    selected_menu_item: Steps,
) -> FlowResult:
    if entry.state != config_entries.ConfigEntryState.LOADED:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Steps.INIT
    assert selected_menu_item in result["menu_options"]

    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": selected_menu_item},
    )


async def initialize_discovery_flow(
    hass: HomeAssistant,
    source_entity: SourceEntity,
    power_profile: PowerProfile | None = None,
    confirm_autodiscovered_model: bool = False,
) -> FlowResult:
    discovery_manager: DiscoveryManager = DiscoveryManager(hass, {})
    if not power_profile:
        power_profile = await get_power_profile(
            hass,
            {},
            await discovery_manager.autodiscover_model(source_entity.entity_entry),
        )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            # CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_NAME: "test",
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MANUFACTURER: power_profile.manufacturer,
            CONF_MODEL: power_profile.model,
            DISCOVERY_SOURCE_ENTITY: source_entity,
            DISCOVERY_POWER_PROFILE: power_profile,
        },
    )
    if not confirm_autodiscovered_model:
        return result

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )


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
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        }
    elif CONF_MODE not in user_input:
        user_input[CONF_MODE] = strategy

    result = await select_menu_item(hass, Steps.VIRTUAL_POWER)
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


async def set_virtual_power_configuration(
    hass: HomeAssistant,
    previous_result: FlowResult,
    basic_options: dict[str, Any] | None = None,
    advanced_options: dict[str, Any] | None = None,
) -> FlowResult:
    if basic_options is None:
        basic_options = {}
    result = await hass.config_entries.flow.async_configure(
        previous_result["flow_id"],
        basic_options,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    if advanced_options is None:
        advanced_options = {}
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        advanced_options,
    )


def create_mock_entry(
    hass: HomeAssistant,
    entry_data: ConfigType,
    source: str = config_entries.SOURCE_USER,
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, source=source)
    entry.add_to_hass(hass)

    assert not entry.options
    return entry


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
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_LEFT,
        }
        | expected_strategy_options
    )
