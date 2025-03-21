import logging

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
    CONF_MULTIPLY_FACTOR,
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
from tests.common import create_input_boolean, create_input_number, run_powercalc_setup

from .common import create_source_entity


async def test_simple_power() -> None:
    source_entity = create_source_entity("switch")
    strategy = FixedStrategy(source_entity, power=50, per_state_power=None)
    assert await strategy.calculate(State(source_entity.entity_id, STATE_ON)) == 50


async def test_template_power(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 42)

    await hass.async_block_till_done()

    template = "{{states('input_number.test')}}"

    source_entity = create_source_entity("switch")
    strategy = await _create_strategy(
        hass,
        {
            CONF_POWER: Template(template),
        },
        source_entity,
    )

    assert await strategy.calculate(State(source_entity.entity_id, STATE_ON)) == 42

    track_entity = strategy.get_entities_to_track()[0]
    assert isinstance(track_entity, TrackTemplate)
    assert track_entity.template.template == template


async def test_states_power(hass: HomeAssistant) -> None:
    source_entity = create_source_entity("media_player")
    strategy = await _create_strategy(
        hass,
        {
            CONF_POWER: 20,
            CONF_STATES_POWER: {"playing": 8.3, "paused": 2.25, "idle": 1.5},
        },
        source_entity,
    )
    assert await strategy.calculate(State(source_entity.entity_id, "playing")) == 8.3
    assert await strategy.calculate(State(source_entity.entity_id, "paused")) == 2.25
    assert await strategy.calculate(State(source_entity.entity_id, "idle")) == 1.5
    assert await strategy.calculate(State(source_entity.entity_id, "whatever")) == 20


async def test_states_power_with_template(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        input_number.DOMAIN,
        {
            input_number.DOMAIN: {
                "test_number42": {"min": "0", "max": "100", "initial": "42"},
                "test_number60": {"min": "0", "max": "100", "initial": "60"},
            },
        },
    )

    await hass.async_block_till_done()

    source_entity = create_source_entity("climate")
    strategy = await _create_strategy(
        hass,
        {
            CONF_STATES_POWER: {
                "heat": Template("{{states('input_number.test_number42')}}"),
                "cool": Template("{{states('input_number.test_number60')}}"),
            },
        },
        source_entity,
    )

    assert await strategy.calculate(State(source_entity.entity_id, "heat")) == 42
    assert await strategy.calculate(State(source_entity.entity_id, "cool")) == 60
    assert not await strategy.calculate(State(source_entity.entity_id, "not_defined"))

    track_entity = strategy.get_entities_to_track()
    assert isinstance(track_entity[0], TrackTemplate)
    assert track_entity[0].template.template == "{{states('input_number.test_number42')}}"
    assert isinstance(track_entity[1], TrackTemplate)
    assert track_entity[1].template.template == "{{states('input_number.test_number60')}}"


async def test_states_power_with_attributes(hass: HomeAssistant) -> None:
    source_entity = create_source_entity("media_player")

    strategy = await _create_strategy(
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

    assert (
        await strategy.calculate(
            State(source_entity.entity_id, "playing", {"media_content_id": "Spotify"}),
        )
        == 5
    )
    assert (
        await strategy.calculate(
            State(source_entity.entity_id, "playing", {"media_content_id": "Youtube"}),
        )
        == 10
    )
    assert (
        await strategy.calculate(
            State(source_entity.entity_id, "playing", {"media_content_id": "Netflix"}),
        )
        == 12
    )


async def test_validation_error_when_no_power_supplied() -> None:
    with pytest.raises(StrategyConfigurationError):
        strategy = FixedStrategy(
            power=None,
            per_state_power=None,
            source_entity=create_source_entity("media_player"),
        )
        await strategy.validate_config()


async def test_validation_error_state_power_only_entity_domain() -> None:
    with pytest.raises(StrategyConfigurationError):
        strategy = FixedStrategy(
            power=20,
            per_state_power=None,
            source_entity=create_source_entity("climate"),
        )
        await strategy.validate_config()


async def test_config_entry_with_template_rendered_correctly(
    hass: HomeAssistant,
) -> None:
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


async def test_config_entry_with_states_power_template(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 30)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "media_player.test",
            CONF_FIXED: {
                CONF_STATES_POWER: {
                    "playing": "{{ states('input_number.test')|float }}",
                    "paused": 1.8,
                },
            },
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("media_player.test", "playing")
    hass.states.async_set("input_number.test", 40)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "40.00"


async def test_template_power_combined_with_multiply_factor(
    hass: HomeAssistant,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/1369
    """

    await create_input_boolean(hass, "test")
    await create_input_number(hass, "test", 30)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {CONF_POWER: "{{states('input_number.test')}}"},
            CONF_MULTIPLY_FACTOR: 100,
        },
    )

    hass.states.async_set("input_boolean.test", STATE_ON)
    hass.states.async_set("input_number.test", "20.5")
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "2050.00"


async def test_template_power_initial_value_after_startup(hass: HomeAssistant) -> None:
    hass.states.async_set("input_number.test", "30")

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_number.test",
            CONF_FIXED: {CONF_POWER: "{{states('input_number.test')}}"},
        },
    )

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "30.00"


async def test_duplicate_tracking_is_prevented(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """
    Make sure the source entity is only tracked once, when it is referenced both in template and entity_id.
    see: https://github.com/bramstroker/homeassistant-powercalc/issues/2802
    """

    caplog.set_level(logging.DEBUG)

    template = """
      {% if state_attr('remote.harmony57', 'current_activity') == 'PowerOff' %}
        12.0
      {% elif state_attr('remote.harmony57', 'current_activity') == 'Listen Radio' %}
        60.0
      {% else %}
        160.0
      {% endif %}
    """

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "remote.harmony57",
            CONF_FIXED: {CONF_POWER: template},
        },
    )

    hass.states.async_set("remote.harmony57", STATE_ON, {"current_activity": "PowerOff"})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.harmony57_power").state == "12.00"

    state_change_logs = [record for record in caplog.records if 'State changed to "on". Power:12.00' in record.message]
    assert len(state_change_logs) == 1, "Expected only one state change log"


async def _create_strategy(
    hass: HomeAssistant,
    config: ConfigType,
    source_entity: SourceEntity,
) -> FixedStrategy:
    factory = PowerCalculatorStrategyFactory(hass)
    strategy_instance = await factory.create(
        {CONF_FIXED: config},
        CalculationStrategy.FIXED,
        None,
        source_entity=source_entity,
    )
    assert isinstance(strategy_instance, FixedStrategy)
    return strategy_instance
