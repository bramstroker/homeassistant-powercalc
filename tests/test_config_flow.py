from selectors import SelectSelector
import pytest
import voluptuous as vol

from typing import Any

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_ENTITY_ID,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from pytest_homeassistant_custom_component.common import MockEntity, MockEntityPlatform, MockConfigEntry, mock_registry
from custom_components.powercalc.config_flow import ConfigFlow, DOMAIN
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR, CONF_CREATE_UTILITY_METERS, CONF_FIXED, CONF_LINEAR, CONF_MANUFACTURER, CONF_MODEL, CONF_MAX_POWER, CONF_POWER_FACTOR, 
    CONF_POWER_TEMPLATE, CONF_MIN_POWER, CONF_MODE, CONF_POWER, CONF_SENSOR_TYPE, CONF_STATES_POWER, CONF_VOLTAGE, CONF_WLED, CalculationStrategy, SensorType
)
from custom_components.test.light import MockLight
from .common import create_mock_light_entity

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

# async def test_create_wled_sensor_entry(hass: HomeAssistant):
#     result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.WLED)

#     result = await hass.config_entries.flow.async_configure(
#         result["flow_id"], {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}
#     )

#     assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
#     _assert_default_virtual_power_entry_data(
#         CalculationStrategy.LINEAR,
#         result["data"],
#         {
#             CONF_WLED: {
#                 CONF_VOLTAGE: 8,
#                 CONF_POWER_FACTOR: 0.8
#             }
#         }
#     )

async def test_lut_manual_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, "234438")
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "belkin", "label": "belkin"} in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MANUFACTURER: "signify"})
    
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_model"
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "LCT010", "label": "LCT010"} in model_options
    assert {"value": "LWB010", "label": "LWB010"} in model_options

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MODEL: "LCT010"})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010"
        }
    )

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

    # Lut has alternate flows depending on auto discovery, don't need to assert here
    if strategy != CalculationStrategy.LUT:
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
