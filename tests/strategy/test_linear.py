from homeassistant.setup import async_setup_component
from homeassistant.core import State
from homeassistant.const import (
    STATE_ON,
    CONF_ATTRIBUTE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from custom_components.powercalc.common import SourceEntity

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.fan import ATTR_PERCENTAGE
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_MAX_POWER,
    CONF_MIN_POWER
)

from custom_components.powercalc.strategy.linear import LinearStrategy
from .common import create_source_entity

async def test_light_max_power_only(hass: HomeAssistant):
    source_entity = create_source_entity("light")
    linear_config = {
        CONF_MAX_POWER: 255
    }
    strategy = LinearStrategy(
        source_entity=source_entity,
        config=linear_config,
        hass=hass,
        standby_power=None
    )
    await strategy.validate_config()

    state = State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 100})
    assert 100 == await strategy.calculate(state)

async def test_fan_min_and_max_power(hass: HomeAssistant):
    source_entity = create_source_entity("fan")
    linear_config = {
        CONF_MIN_POWER: 10,
        CONF_MAX_POWER: 100
    }
    strategy = LinearStrategy(
        source_entity=source_entity,
        config=linear_config,
        hass=hass,
        standby_power=None
    )
    await strategy.validate_config()

    state = State(source_entity.entity_id, STATE_ON, {ATTR_PERCENTAGE: 50})
    assert 55 == await strategy.calculate(state)

async def test_light_calibrate(hass: HomeAssistant):
    source_entity = create_source_entity("light")
    linear_config = {
        CONF_CALIBRATE: [
            "1 -> 0.3",
            "10 -> 1.25",
            "50 -> 3.50",
            "100 -> 6.8",
            "255 -> 15.3"
        ]
    }
    strategy = LinearStrategy(
        source_entity=source_entity,
        config=linear_config,
        hass=hass,
        standby_power=None
    )

    await strategy.validate_config()

    assert 0.3 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 1}))
    assert 1.25 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 10}))
    assert 2.375 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 30}))
    assert 5.15 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 75}))
    assert 15.3 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255}))

    # set to some out of bound brightness.
    assert 15.3 == await strategy.calculate(State(source_entity.entity_id, STATE_ON, {ATTR_BRIGHTNESS: 350}))

async def test_custom_attribute(hass: HomeAssistant):
    source_entity = create_source_entity("fan")
    linear_config = {
        CONF_ATTRIBUTE: "my_attribute",
        CONF_MIN_POWER: 20,
        CONF_MAX_POWER: 100
    }
    strategy = LinearStrategy(
        source_entity=source_entity,
        config=linear_config,
        hass=hass,
        standby_power=None
    )

    await strategy.validate_config()

    state = State(source_entity.entity_id, STATE_ON, {"my_attribute": 40})
    assert 52 == await strategy.calculate(state)