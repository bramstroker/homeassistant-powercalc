import pytest
from homeassistant.components import input_number
from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.strategy.fixed import FixedStrategy

from ..common import create_input_boolean, create_input_number
from .common import create_source_entity


async def test_simple_power():
    source_entity = create_source_entity("switch")
    strategy = FixedStrategy(source_entity, power=50, per_state_power=None)
    assert 50 == await strategy.calculate(State(source_entity.entity_id, STATE_ON))


async def test_template_power(hass: HomeAssistant):
    await create_input_number(hass, "test", 42)

    await hass.async_block_till_done()

    template = "{{states('input_number.test')}}"

    source_entity = create_source_entity("switch")
    strategy = _create_strategy(
        hass,
        {
            CONF_POWER: Template(template),
        },
        source_entity,
    )

    assert 42 == await strategy.calculate(State(source_entity.entity_id, STATE_ON))

    track_entity = strategy.get_entities_to_track()[0]
    assert isinstance(track_entity, TrackTemplate)
    assert track_entity.template.template == template


async def test_states_power(hass: HomeAssistant):
    source_entity = create_source_entity("media_player")
    strategy = _create_strategy(
        hass,
        {
            CONF_POWER: 20,
            CONF_STATES_POWER: {"playing": 8.3, "paused": 2.25, "idle": 1.5},
        },
        source_entity,
    )
    assert 8.3 == await strategy.calculate(State(source_entity.entity_id, "playing"))
    assert 2.25 == await strategy.calculate(State(source_entity.entity_id, "paused"))
    assert 1.5 == await strategy.calculate(State(source_entity.entity_id, "idle"))
    assert 20 == await strategy.calculate(State(source_entity.entity_id, "whatever"))


async def test_states_power_with_template(hass: HomeAssistant):
    assert await async_setup_component(
        hass,
        input_number.DOMAIN,
        {
            input_number.DOMAIN: {
                "test_number42": {"min": "0", "max": "100", "initial": "42"},
                "test_number60": {"min": "0", "max": "100", "initial": "60"},
            }
        },
    )

    await hass.async_block_till_done()

    source_entity = create_source_entity("climate")
    strategy = _create_strategy(
        hass,
        {
            CONF_STATES_POWER: {
                "heat": Template("{{states('input_number.test_number42')}}"),
                "cool": Template("{{states('input_number.test_number60')}}"),
            }
        },
        source_entity,
    )

    assert 42 == await strategy.calculate(State(source_entity.entity_id, "heat"))
    assert 60 == await strategy.calculate(State(source_entity.entity_id, "cool"))
    assert not await strategy.calculate(State(source_entity.entity_id, "not_defined"))

    track_entity = strategy.get_entities_to_track()
    assert isinstance(track_entity[0], TrackTemplate)
    assert (
        track_entity[0].template.template == "{{states('input_number.test_number42')}}"
    )
    assert isinstance(track_entity[1], TrackTemplate)
    assert (
        track_entity[1].template.template == "{{states('input_number.test_number60')}}"
    )


async def test_states_power_with_attributes(hass: HomeAssistant):
    source_entity = create_source_entity("media_player")

    strategy = _create_strategy(
        hass,
        {
            CONF_POWER: 12,
            CONF_STATES_POWER: {
                "media_content_id|Spotify": 5,
                "media_content_id|Youtube": 10,
            },
        },
        source_entity,
    )

    assert 5 == await strategy.calculate(
        State(source_entity.entity_id, "playing", {"media_content_id": "Spotify"})
    )
    assert 10 == await strategy.calculate(
        State(source_entity.entity_id, "playing", {"media_content_id": "Youtube"})
    )
    assert 12 == await strategy.calculate(
        State(source_entity.entity_id, "playing", {"media_content_id": "Netflix"})
    )


async def test_validation_error_when_no_power_supplied():
    with pytest.raises(StrategyConfigurationError):
        strategy = FixedStrategy(
            power=None,
            per_state_power=None,
            source_entity=create_source_entity("media_player"),
        )
        await strategy.validate_config()


async def test_validation_error_state_power_only_entity_domain():
    with pytest.raises(StrategyConfigurationError):
        strategy = FixedStrategy(
            power=20,
            per_state_power=None,
            source_entity=create_source_entity("climate"),
        )
        await strategy.validate_config()


async def test_config_entry_with_template_rendered_correctly(hass: HomeAssistant):
    await create_input_boolean(hass, "test")
    await create_input_number(hass, "test", 30)

    template = "{{states('input_number.test')|float}}"
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {
                CONF_POWER: template,
                CONF_POWER_TEMPLATE: template,
            },
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("input_boolean.test", STATE_ON)
    hass.states.async_set("input_number.test", 40)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "40.00"


def _create_strategy(
    hass: HomeAssistant, config: ConfigType, source_entity: SourceEntity
) -> FixedStrategy:
    factory = PowerCalculatorStrategyFactory(hass)
    strategy_instance = factory.create(
        {CONF_FIXED: config},
        CalculationStrategy.FIXED,
        None,
        source_entity=source_entity,
    )
    assert isinstance(strategy_instance, FixedStrategy)
    return strategy_instance
