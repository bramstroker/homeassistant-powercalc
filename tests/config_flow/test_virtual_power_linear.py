from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_GAMMA_CURVE,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_VALUE,
    CalculationStrategy,
    SensorType,
)
from tests.common import create_mock_config_entry
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
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

    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_calibrate_list(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await set_virtual_power_configuration(
        hass,
        result,
        {
            CONF_CALIBRATE: [
                {CONF_VALUE: 1, CONF_POWER: 10},
                {CONF_VALUE: 20, CONF_POWER: 25},
                {CONF_VALUE: 40, CONF_POWER: 50},
            ],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_create_linear_sensor_error_mandatory_fields(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MIN_POWER: 20},
    )

    assert result["errors"]
    assert result["errors"]["base"] == "linear_mandatory"
    assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_linear_options_flow(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 10, CONF_MAX_POWER: 40},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LINEAR)
    schema_keys = [key.schema for key in result["data_schema"].schema]
    assert CONF_MIN_POWER in schema_keys
    assert CONF_MAX_POWER in schema_keys
    assert CONF_GAMMA_CURVE in schema_keys
    assert CONF_CALIBRATE in schema_keys

    user_input = {CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LINEAR][CONF_MAX_POWER] == 50


async def test_linear_options_hidden_from_menu_for_self_usage_profiles(hass: HomeAssistant) -> None:
    """
    Fixed options should be hidden from the menu for self usage profiles
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2935
    """
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "smart_dimmer_with_pm",
        },
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    menu_options = result["menu_options"]
    assert Step.LINEAR not in menu_options


async def test_linear_options_flow_error(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 40, CONF_MAX_POWER: 50},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LINEAR)

    user_input = {CONF_MIN_POWER: 55, CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"]["base"] == "linear_min_higher_as_max"
