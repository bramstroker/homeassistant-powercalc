import logging

import pytest
from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import CONF_ATTRIBUTE, CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.typing import ConfigType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_SENSOR_TYPE,
    CONF_LINEAR,
    DOMAIN,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.linear import LinearStrategy
from custom_components.test.light import MockLight

from .common import create_source_entity
from ..common import create_mock_light_entity


async def test_light_max_power_only(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass, create_source_entity("light"), {CONF_MAX_POWER: 255}
    )

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 100})
    assert 100 == await strategy.calculate(state)


async def test_fan_min_and_max_power(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass, create_source_entity("fan"), {CONF_MIN_POWER: 10, CONF_MAX_POWER: 100}
    )

    state = State("fan.test", STATE_ON, {ATTR_PERCENTAGE: 50})
    assert 55 == await strategy.calculate(state)


async def test_light_calibrate(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass,
        create_source_entity("light"),
        {
            CONF_CALIBRATE: [
                "1 -> 0.3",
                "10 -> 1.25",
                "50 -> 3.50",
                "100 -> 6.8",
                "255 -> 15.3",
            ]
        },
    )

    entity_id = "light.test"
    assert 0.3 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 1})
    )
    assert 1.25 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 10})
    )
    assert 2.375 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 30})
    )
    assert 5.15 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 75})
    )
    assert 15.3 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    )

    # set to some out of bound brightness.
    assert 15.3 == await strategy.calculate(
        State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 350})
    )


async def test_custom_attribute(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass,
        create_source_entity("fan"),
        {CONF_ATTRIBUTE: "my_attribute", CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("fan.test", STATE_ON, {"my_attribute": 40})
    assert 52 == await strategy.calculate(state)


async def test_power_is_none_when_state_is_none(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass, create_source_entity("light"), {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100}
    )

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: None})
    assert not await strategy.calculate(state)


async def test_error_on_non_number_state(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    strategy = await _create_strategy_instance(
        hass,
        create_source_entity("sensor"),
        {CONF_CALIBRATE: ["1 -> 0.3", "10 -> 1.25"]},
    )

    state = State("sensor.test", "foo")
    assert not await strategy.calculate(state)
    assert "Expecting state to be a number for entity" in caplog.text


async def test_validate_raises_exception_not_allowed_domain(hass: HomeAssistant):
    with pytest.raises(StrategyConfigurationError):
        await _create_strategy_instance(
            hass,
            create_source_entity("sensor"),
            {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
        )


async def test_validate_raises_exception_when_min_power_higher_than_max(
    hass: HomeAssistant,
):
    with pytest.raises(StrategyConfigurationError):
        await _create_strategy_instance(
            hass,
            create_source_entity("light"),
            {CONF_MIN_POWER: 150, CONF_MAX_POWER: 100},
        )


async def test_lower_value_than_calibration_table_defines(hass: HomeAssistant):
    strategy = await _create_strategy_instance(
        hass,
        create_source_entity("light"),
        {
            CONF_CALIBRATE: [
                "50 -> 5",
                "100 -> 8",
                "255 -> 15",
            ]
        },
    )
    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 20})
    assert 3.52 == pytest.approx(float(await strategy.calculate(state)), 0.01)


async def _create_strategy_instance(
    hass: HomeAssistant, source_entity: SourceEntity, linear_config: ConfigType
) -> LinearStrategy:
    strategy = LinearStrategy(
        source_entity=source_entity, config=linear_config, hass=hass, standby_power=None
    )

    await strategy.validate_config()

    return strategy


async def test_config_entry_with_calibrate_list(hass: HomeAssistant):
    light_entity = MockLight("test")
    await create_mock_light_entity(hass, light_entity)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_LINEAR: {
                CONF_CALIBRATE: {
                    "1": 0.4,
                    "25": 1.2,
                    "100": 3,
                    "255": 5.3
                }
            },
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 25})
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "1.20"