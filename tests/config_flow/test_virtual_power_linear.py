from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    set_virtual_power_configuration,
)


async def test_create_linear_sensor_entry(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.LINEAR,
        result["data"],
        {CONF_LINEAR: {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_linear_sensor_error_mandatory_fields(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await set_virtual_power_configuration(hass, result, {CONF_MIN_POWER: 20})

    assert result["errors"]
    assert result["errors"]["base"] == "linear_mandatory"
    assert result["type"] == data_entry_flow.FlowResultType.FORM

async def test_linear_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 10, CONF_MAX_POWER: 40},
        },
    )

    result = await initialize_options_flow(hass, entry)

    user_input = {CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LINEAR][CONF_MAX_POWER] == 50


async def test_linear_options_flow_error(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 40, CONF_MAX_POWER: 50},
        },
    )

    result = await initialize_options_flow(hass, entry)

    user_input = {CONF_MIN_POWER: 55, CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"]["base"] == "linear_min_higher_as_max"
