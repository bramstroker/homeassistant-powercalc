import pytest

from typing import Any

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_ENTITY_ID
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.powercalc.config_flow import ConfigFlow, DOMAIN
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR, CONF_CREATE_UTILITY_METERS, CONF_FIXED, CONF_LINEAR, CONF_MAX_POWER, 
    CONF_POWER_TEMPLATE, CONF_MIN_POWER, CONF_MODE, CONF_POWER, CONF_SENSOR_TYPE, CONF_STATES_POWER, CalculationStrategy, SensorType
)

DEFAULT_ENTITY_ID = "light.test"
DEFAULT_UNIQUE_ID = "7c009ef6829f"

# @patch("custom_components.volkswagencarnet.config_flow.Connection")
async def test_sensor_type_menu_displayed(hass: HomeAssistant):
    """Test a menu is diplayed with sensor type selection"""

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == "user"

@pytest.mark.parametrize(
    "sensor_type",
    [
        SensorType.VIRTUAL_POWER,
        SensorType.DAILY_ENERGY,
        SensorType.GROUP
    ],
)
async def test_sensor_type_form_displayed(hass: HomeAssistant, sensor_type: SensorType):
    await _select_sensor_type(hass, sensor_type)

async def test_create_fixed_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER: 20}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {
                CONF_POWER: 20
            }
        }
    )

async def test_create_fixed_sensor_entry_with_template(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_TEMPLATE: "{states(input.my_boolean} | float"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {
                CONF_POWER: "{states(input.my_boolean} | float",
                CONF_POWER_TEMPLATE: "{states(input.my_boolean} | float"
            }
        }
    )

async def test_create_fixed_sensor_entry_with_states_power(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATES_POWER: ""}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {
                CONF_STATES_POWER: ""
            }
        }
    )

async def test_create_linear_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LINEAR,
        result["data"],
        {
            CONF_LINEAR: {
                CONF_MIN_POWER: 1,
                CONF_MAX_POWER: 40
            }
        }
    )

async def test_create_linear_sensor_error_mandatory_fields(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIN_POWER: 20}
    )

    assert result["errors"]
    assert result["errors"]["base"] == "linear_mandatory"
    assert result["type"] == data_entry_flow.FlowResultType.FORM

def _assert_default_virtual_power_entry_data(
    strategy: CalculationStrategy,
    config_entry_data: dict,
    expected_strategy_options = dict[str, Any]
):
    assert config_entry_data == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MODE: strategy,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_NAME: "test",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    } | expected_strategy_options

async def _goto_virtual_power_strategy_step(
    hass: HomeAssistant,
    strategy: CalculationStrategy,
    user_input: dict[str, Any] | None = None
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

    result = await _select_sensor_type(hass, "virtual_power")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["step_id"] == strategy
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    return result

async def _select_sensor_type(hass: HomeAssistant, sensor_type: SensorType) -> FlowResult:
    """Select a sensor type from the menu"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": sensor_type}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == sensor_type

    return result
