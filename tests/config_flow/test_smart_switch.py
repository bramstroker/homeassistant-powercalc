from typing import Any

import pytest
import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_POWER
from custom_components.powercalc.config_flow import CONF_CONFIRM_AUTODISCOVERED_MODEL, Steps
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SELF_USAGE_INCLUDED,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)
from tests.conftest import MockEntityWithModel


@pytest.mark.parametrize(
    "user_input,expected_fixed_power",
    [
        ({CONF_POWER: 20, CONF_SELF_USAGE_INCLUDED: True}, 20.82),
        ({CONF_POWER: 20, CONF_SELF_USAGE_INCLUDED: False}, 20),
        ({CONF_POWER: 20}, 20.82),
        ({}, 0.82),
    ],
)
async def test_smart_switch_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    user_input: dict[str, Any],
    expected_fixed_power: float,
) -> None:
    mock_entity_with_model_information(
        "switch.test",
        "shelly",
        "Shelly Plug S",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await select_menu_item(hass, Steps.MENU_LIBRARY)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_CREATE_UTILITY_METERS: False,
            CONF_CREATE_ENERGY_SENSOR: False,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.LIBRARY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.SMART_SWITCH

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.POWER_ADVANCED

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FIXED][CONF_POWER] == expected_fixed_power
    assert result["data"][CONF_MODE] == CalculationStrategy.FIXED

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_device_power")
    assert power_state.state == f"{expected_fixed_power:.2f}"


async def test_smart_switch_options(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_SELF_USAGE_INCLUDED: False,
            CONF_FIXED: {CONF_POWER: 40},
            CONF_MANUFACTURER: "shelly",
            CONF_MODEL: "Shelly Plug S",
        },
    )

    result = await initialize_options_flow(hass, entry, Steps.FIXED)

    user_input = {CONF_POWER: 50, CONF_SELF_USAGE_INCLUDED: True}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_SELF_USAGE_INCLUDED] is True
    assert entry.data[CONF_POWER] == 50
    assert entry.data[CONF_FIXED][CONF_POWER] == 50.82


async def test_smart_switch_options_correctly_loaded(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_POWER: 40,
            CONF_FIXED: {CONF_POWER: 40.85},
            CONF_SELF_USAGE_INCLUDED: True,
            CONF_MANUFACTURER: "shelly",
            CONF_MODEL: "Shelly Plug S",
        },
    )

    result = await initialize_options_flow(hass, entry, Steps.FIXED)

    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_SELF_USAGE_INCLUDED)].description == {
        "suggested_value": True,
    }
    assert schema_keys[schema_keys.index(CONF_POWER)].description == {
        "suggested_value": 40,
    }
