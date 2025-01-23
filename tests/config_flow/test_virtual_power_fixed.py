from unittest.mock import patch

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR, CONF_FIXED, CONF_POWER_TEMPLATE
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    ENERGY_INTEGRATION_METHOD_RIGHT,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from tests.common import get_test_config_dir, run_powercalc_setup
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    process_config_flow,
    select_menu_item,
    set_virtual_power_configuration,
)


async def test_create_fixed_sensor_entry(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    result = await set_virtual_power_configuration(hass, result, {CONF_POWER: 20})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER: 20}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_template(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    template = "{{states(input_number.my_number)}} | float"
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER_TEMPLATE: template},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER_TEMPLATE: template}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_states_power(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_STATES_POWER: {"playing": 1.8}},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_STATES_POWER: {"playing": 1.8}}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_fixed_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)

    schema_keys = list(result["data_schema"].schema.keys())
    assert schema_keys == [CONF_ENTITY_ID, CONF_STANDBY_POWER, CONF_CREATE_ENERGY_SENSOR, CONF_CREATE_UTILITY_METERS]

    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ENTITY_ID: "light.test", CONF_CREATE_UTILITY_METERS: True},
    )

    result = await initialize_options_flow(hass, entry, Step.FIXED)

    user_input = {CONF_POWER: 50}
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    result = await initialize_options_flow(hass, entry, Step.ADVANCED_OPTIONS)
    user_input = {CONF_IGNORE_UNAVAILABLE_STATE: True}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_POWER] == 50
    assert entry.data[CONF_CREATE_UTILITY_METERS]
    assert entry.data[CONF_IGNORE_UNAVAILABLE_STATE]


async def test_fixed_options_hidden_from_menu_for_self_usage_profiles(hass: HomeAssistant) -> None:
    """
    Fixed options should be hidden from the menu for self usage profiles
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2935
    """
    hass.config.config_dir = get_test_config_dir()
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "power_meter",
        },
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    menu_options = result["menu_options"]
    assert Step.FIXED not in menu_options


async def test_strategy_raises_unknown_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.powercalc.strategy.fixed.FixedStrategy.validate_config",
        side_effect=StrategyConfigurationError("test"),
    ):
        result = await goto_virtual_power_strategy_step(
            hass,
            CalculationStrategy.FIXED,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_POWER: 20},
        )

        assert result["errors"]
        assert result["errors"]["base"] == "unknown"
        assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_advanced_power_configuration_can_be_set(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    advanced_options = {
        CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
    }

    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER: 20},
        advanced_options,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {CONF_POWER: 20},
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
        },
    )


async def test_entity_selection_mandatory(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.VIRTUAL_POWER)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODE: CalculationStrategy.FIXED,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"entity_id": "entity_mandatory"}


async def test_global_configuration_is_applied_to_field_default(
    hass: HomeAssistant,
) -> None:
    """Field should be set to match powercalc global configuration by default"""
    global_config = {
        CONF_CREATE_UTILITY_METERS: True,
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_RIGHT,
        CONF_IGNORE_UNAVAILABLE_STATE: True,
    }
    await run_powercalc_setup(hass, {}, global_config)

    result = await select_menu_item(hass, Step.VIRTUAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_CREATE_UTILITY_METERS)].description == {
        "suggested_value": True,
    }

    result = await process_config_flow(
        hass,
        result,
        {
            Step.VIRTUAL_POWER: {
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_ENTITY_ID: "light.test",
            },
            Step.FIXED: {
                CONF_POWER: 20,
            },
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.POWER_ADVANCED
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_ENERGY_INTEGRATION_METHOD)].default() == ENERGY_INTEGRATION_METHOD_RIGHT
    assert schema_keys[schema_keys.index(CONF_IGNORE_UNAVAILABLE_STATE)].description == {"suggested_value": True}


async def test_sensor_is_created_without_providing_source_entity(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_NAME: "My nice sensor",
        },
    )
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER: 20},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_nice_sensor_power")
    assert hass.states.get("sensor.my_nice_sensor_energy")


async def test_setup_twice_for_same_entity(hass: HomeAssistant) -> None:
    """
    Test that we can set up two virtual power sensors for the same entity.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2684
    """
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={CONF_NAME: "My nice sensor", CONF_ENTITY_ID: "light.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER: 20},
    )

    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={CONF_NAME: "My nice sensor 2", CONF_ENTITY_ID: "light.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER: 20},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_nice_sensor_power")
    assert hass.states.get("sensor.my_nice_sensor_2_power")
