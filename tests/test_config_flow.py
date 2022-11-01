from typing import Any, Mapping
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.components import sensor
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    POWER_WATT,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.config_flow import (
    CONF_CONFIRM_AUTODISCOVERED_MODEL,
    DOMAIN,
)
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_FIXED,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_FACTOR,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    CONF_SUB_PROFILE,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VOLTAGE,
    CONF_WLED,
    ENERGY_INTEGRATION_METHOD_LEFT,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.test.light import MockLight

from .common import (
    MockConfigEntry,
    create_mock_light_entity,
    create_mocked_virtual_power_sensor_entry,
)

DEFAULT_ENTITY_ID = "light.test"
DEFAULT_UNIQUE_ID = "7c009ef6829f"


async def test_discovery_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    light_entity.manufacturer = "signify"
    light_entity.model = "LCT010"
    await create_mock_light_entity(hass, light_entity)

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_NAME: "test",
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
    )

    # Confirm selected manufacturer/model
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONFIRM_AUTODISCOVERED_MODEL: True}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "signify",
        CONF_MODEL: "LCT010",
        CONF_NAME: "test",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    }


async def test_sensor_type_menu_displayed(hass: HomeAssistant):
    """Test a menu is diplayed with sensor type selection"""

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == "user"


@pytest.mark.parametrize(
    "sensor_type",
    [SensorType.VIRTUAL_POWER, SensorType.DAILY_ENERGY, SensorType.GROUP],
)
async def test_sensor_type_form_displayed(hass: HomeAssistant, sensor_type: SensorType):
    await _select_sensor_type(hass, sensor_type)


async def test_create_fixed_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    result = await _set_virtual_power_configuration(hass, result, {CONF_POWER: 20})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED, result["data"], {CONF_FIXED: {CONF_POWER: 20}}
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_template(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    template = "{states(input_number.my_number} | float"
    result = await _set_virtual_power_configuration(
        hass, result, {CONF_POWER_TEMPLATE: template}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER: template, CONF_POWER_TEMPLATE: template}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_states_power(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    result = await _set_virtual_power_configuration(
        hass, result, {CONF_STATES_POWER: ""}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED, result["data"], {CONF_FIXED: {CONF_STATES_POWER: ""}}
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_linear_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await _set_virtual_power_configuration(
        hass, result, {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LINEAR,
        result["data"],
        {CONF_LINEAR: {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_linear_sensor_error_mandatory_fields(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await _set_virtual_power_configuration(hass, result, {CONF_MIN_POWER: 20})

    assert result["errors"]
    assert result["errors"]["base"] == "linear_mandatory"
    assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_create_wled_sensor_entry(hass: HomeAssistant):
    await _create_wled_entities(hass)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.WLED)
    result = await _set_virtual_power_configuration(
        hass, result, {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.WLED,
        result["data"],
        {CONF_WLED: {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_manual_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "belkin", "label": "belkin"} in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MANUFACTURER: "signify"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_model"
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "LCT010", "label": "LCT010"} in model_options
    assert {"value": "LWB010", "label": "LWB010"} in model_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODEL: "LCT010"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM

    # Advanced options step
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: "signify", CONF_MODEL: "LCT010"},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_autodiscover_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    light_entity.manufacturer = "ikea"
    light_entity.model = "LED1545G12"
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut"

    result = await _set_virtual_power_configuration(
        hass, result, {CONF_CONFIRM_AUTODISCOVERED_MODEL: True}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: light_entity.manufacturer, CONF_MODEL: light_entity.model},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_not_autodiscovered_model_unsupported(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON)
    light_entity.manufacturer = "ikea"
    # Set to model which is not in library
    light_entity.model = "unknown_model"
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"


async def test_lut_not_autodiscovered(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON)
    light_entity._attr_unique_id = None
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"


async def test_lut_autodiscover_flow_not_confirmed(hass: HomeAssistant):
    """
    When manufacturer and model are auto detected and user chooses to not accept it,
    make sure he/she is forwarded to the manufacturer listing
    """
    light_entity = MockLight("test", STATE_ON, "234438")
    light_entity.manufacturer = "ikea"
    light_entity.model = "LED1545G12"
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONFIRM_AUTODISCOVERED_MODEL: False}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"


async def test_lut_flow_with_sub_profiles(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MANUFACTURER: "yeelight"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODEL: "YLDL01YL"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_subprofile"
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["sub_profile"]
    select_options = model_select.config["options"]
    assert {"value": "ambilight", "label": "ambilight"} in select_options
    assert {"value": "downlight", "label": "downlight"} in select_options

    result = await _set_virtual_power_configuration(
        hass, result, {CONF_SUB_PROFILE: "ambilight"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: "yeelight", CONF_MODEL: "YLDL01YL/ambilight"},
    )


async def test_advanced_power_configuration_can_be_set(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    advanced_options = {
        CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}"
    }

    result = await _set_virtual_power_configuration(
        hass, result, {CONF_POWER: 20}, advanced_options
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {CONF_POWER: 20},
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
        },
    )


async def test_daily_energy_mandatory_fields_not_supplied(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {CONF_NAME: "My daily energy sensor"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"] == {"base": "daily_energy_mandatory"}


async def test_create_daily_energy_entry(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 0.5,
        CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
        CONF_NAME: "My daily energy sensor",
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UPDATE_FREQUENCY: 1800,
            CONF_VALUE: 0.5,
            CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
        },
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_daily_energy_sensor_energy")


async def test_create_group_entry(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_CREATE_UTILITY_METERS: False,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_create_group_entry_without_unique_id(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power"],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power"],
        CONF_UNIQUE_ID: "My group sensor",
        CONF_CREATE_UTILITY_METERS: False,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_can_select_existing_powercalc_entry_as_group_member(hass: HomeAssistant):
    """
    Test if we can select previously created virtual power config entries as the group member.
    Only entries with a unique ID must be selectable
    """

    config_entry_1 = await create_mocked_virtual_power_sensor_entry(
        hass, "VirtualPower1", "abcdef"
    )
    config_entry_2 = await create_mocked_virtual_power_sensor_entry(
        hass, "VirtualPower2", None
    )
    config_entry_3 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "abcdefg",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        title="VirtualPower3",
    )
    config_entry_3.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_3.entry_id)
    await hass.async_block_till_done()

    result = await _select_sensor_type(hass, SensorType.GROUP)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    data_schema: vol.Schema = result["data_schema"]
    select: SelectSelector = data_schema.schema[CONF_GROUP_MEMBER_SENSORS]
    options = select.config["options"]
    assert {"value": config_entry_1.entry_id, "label": "VirtualPower1"} in options
    assert {"value": config_entry_2.entry_id, "label": "VirtualPower2"} not in options

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_CREATE_UTILITY_METERS: False,
    }


async def test_group_error_mandatory(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.GROUP)
    user_input = {CONF_NAME: "My group sensor", CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"]["base"] == "group_mandatory"


async def test_fixed_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_POWER] == 50


async def test_wled_options_flow(hass: HomeAssistant):
    await _create_wled_entities(hass)

    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.WLED,
            CONF_WLED: {CONF_VOLTAGE: 5},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_VOLTAGE: 12}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_WLED][CONF_VOLTAGE] == 12


async def test_linear_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 10, CONF_MAX_POWER: 40},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LINEAR][CONF_MAX_POWER] == 50


async def test_daily_energy_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_NAME: "My daily energy sensor",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 50},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_VALUE: 75, CONF_UNIT_OF_MEASUREMENT: POWER_WATT}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_UNIT_OF_MEASUREMENT] == POWER_WATT
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_VALUE] == 75


async def test_lut_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LUT,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_CREATE_ENERGY_SENSOR: False}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_CREATE_ENERGY_SENSOR]


async def test_group_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_NAME: "Kitchen",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_POWER_ENTITIES: ["sensor.fridge_power"],
        },
    )

    result = await _initialize_options_flow(hass, entry)

    new_entities = ["sensor.fridge_power", "sensor.kitchen_lights_power"]
    user_input = {CONF_GROUP_POWER_ENTITIES: new_entities}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_GROUP_POWER_ENTITIES] == new_entities

    # assert hass.states.get("sensor.kitchen_power").attributes.get(ATTR_ENTITIES) == new_entities


async def test_linear_options_flow_error(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 40, CONF_MAX_POWER: 50},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_MIN_POWER: 55, CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"]["base"] == "linear_min_higher_as_max"


async def test_strategy_raises_unknown_error(hass: HomeAssistant):
    with patch(
        "custom_components.powercalc.strategy.fixed.FixedStrategy.validate_config",
        side_effect=StrategyConfigurationError("test"),
    ):
        result = await _goto_virtual_power_strategy_step(
            hass, CalculationStrategy.FIXED
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_POWER: 20}
        )

        assert result["errors"]
        assert result["errors"]["base"] == "unknown"
        assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_autodiscovered_option_flow(hass: HomeAssistant):
    """
    Test that we can open an option flow for an auto discovered config entry
    """
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_NAME: "Test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
        config_entries.SOURCE_INTEGRATION_DISCOVERY,
    )

    result = await _initialize_options_flow(hass, entry)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {CONF_CREATE_ENERGY_SENSOR: False}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_CREATE_ENERGY_SENSOR]


def _create_mock_entry(
    hass: HomeAssistant,
    entry_data: ConfigType,
    source: str = config_entries.SOURCE_USER,
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, source=source)
    entry.add_to_hass(hass)

    assert not entry.options
    return entry


async def _initialize_options_flow(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> FlowResult:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    return result


def _assert_default_virtual_power_entry_data(
    strategy: CalculationStrategy,
    config_entry_data: Mapping[str, Any],
    expected_strategy_options: dict,
):
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


async def _goto_virtual_power_strategy_step(
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

    result = await _select_sensor_type(hass, SensorType.VIRTUAL_POWER)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    # Lut has alternate flows depending on auto discovery, don't need to assert here
    if strategy != CalculationStrategy.LUT:
        assert result["step_id"] == strategy
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    return result


async def _set_virtual_power_configuration(
    hass: HomeAssistant,
    previous_result: FlowResult,
    basic_options: dict[str, Any] | None = None,
    advanced_options: dict[str, Any] | None = None,
) -> FlowResult:
    if basic_options is None:
        basic_options = {}
    result = await hass.config_entries.flow.async_configure(
        previous_result["flow_id"], basic_options
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    if advanced_options is None:
        advanced_options = {}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], advanced_options
    )
    return result


async def _select_sensor_type(
    hass: HomeAssistant, sensor_type: SensorType
) -> FlowResult:
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


async def _create_wled_entities(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current", native_value="5.0", unique_id=DEFAULT_UNIQUE_ID
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass, sensor.DOMAIN, {sensor.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()
