from homeassistant import data_entry_flow
from homeassistant.components import sensor
from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER_FACTOR,
    CONF_SENSOR_TYPE,
    CONF_VOLTAGE,
    CONF_WLED,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight
from tests.common import create_mock_light_entity
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    assert_default_virtual_power_entry_data,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    set_virtual_power_configuration,
)


async def test_create_wled_sensor_entry(hass: HomeAssistant) -> None:
    await _create_wled_entities(hass)

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.WLED)
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.WLED,
        result["data"],
        {CONF_WLED: {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_wled_options_flow(hass: HomeAssistant) -> None:
    await _create_wled_entities(hass)

    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.WLED,
            CONF_MANUFACTURER: "WLED",
            CONF_MODEL: "FOSS",
            CONF_WLED: {CONF_VOLTAGE: 5},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.WLED)

    user_input = {CONF_VOLTAGE: 12}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_WLED][CONF_VOLTAGE] == 12


async def _create_wled_entities(hass: HomeAssistant) -> None:
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current",
        native_value="5.0",
        unique_id=DEFAULT_UNIQUE_ID,
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: {CONF_PLATFORM: "test"}},
    )
    await hass.async_block_till_done()
