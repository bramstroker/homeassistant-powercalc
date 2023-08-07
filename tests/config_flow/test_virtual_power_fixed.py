from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_FIXED, CONF_POWER_TEMPLATE
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_MODE,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    select_sensor_type,
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
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    result = await initialize_options_flow(hass, entry)

    user_input = {CONF_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_POWER] == 50


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
    result = await select_sensor_type(hass, SensorType.VIRTUAL_POWER)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODE: CalculationStrategy.FIXED,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"entity_id": "entity_mandatory"}
