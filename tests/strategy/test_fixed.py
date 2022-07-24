from homeassistant.components import input_number
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.helpers.event import TrackTemplate

from custom_components.powercalc.strategy.fixed import FixedStrategy

from .common import create_source_entity


async def test_simple_power():
    source_entity = create_source_entity("switch")
    strategy = FixedStrategy(source_entity, power=50, per_state_power=None)
    assert 50 == await strategy.calculate(State(source_entity.entity_id, STATE_ON))


async def test_template_power(hass: HomeAssistant):
    assert await async_setup_component(
        hass,
        input_number.DOMAIN,
        {"input_number": {"test": {"min": "0", "max": "100", "initial": "42"}}},
    )

    await hass.async_block_till_done()

    template = "{{states('input_number.test')}}"

    source_entity = create_source_entity("switch")
    strategy = FixedStrategy(
        source_entity,
        power=Template(template, hass),
        per_state_power=None,
    )

    assert 42 == await strategy.calculate(State(source_entity.entity_id, STATE_ON))

    track_entity = strategy.get_entities_to_track()[0]
    assert isinstance(track_entity, TrackTemplate)
    track_entity.template == template


async def test_states_power():
    source_entity = create_source_entity("media_player")

    strategy = FixedStrategy(
        source_entity,
        power=20,
        per_state_power={"playing": 8.3, "paused": 2.25, "idle": 1.5},
    )
    assert 8.3 == await strategy.calculate(State(source_entity.entity_id, "playing"))
    assert 2.25 == await strategy.calculate(State(source_entity.entity_id, "paused"))
    assert 1.5 == await strategy.calculate(State(source_entity.entity_id, "idle"))
    assert 20 == await strategy.calculate(State(source_entity.entity_id, "whatever"))

async def test_states_power_with_template(hass: HomeAssistant):
    assert await async_setup_component(
        hass,
        input_number.DOMAIN, {
            input_number.DOMAIN: {
                "test_number42": {"min": "0", "max": "100", "initial": "42"},
                "test_number60": {"min": "0", "max": "100", "initial": "60"}
            }
        },
    )

    await hass.async_block_till_done()

    source_entity = create_source_entity("climate")

    strategy = FixedStrategy(
        source_entity,
        power=None,
        per_state_power={
            "heat": Template("{{states('input_number.test_number42')}}", hass),
            "cool": Template("{{states('input_number.test_number60')}}", hass),
        },
    )
    assert 42 == await strategy.calculate(State(source_entity.entity_id, "heat"))
    assert 60 == await strategy.calculate(State(source_entity.entity_id, "cool"))

    track_entity = strategy.get_entities_to_track()
    assert isinstance(track_entity[0], TrackTemplate)
    track_entity[0].template == "{{states('input_number.test_number42')}}"
    assert isinstance(track_entity[1], TrackTemplate)
    track_entity[1].template == "{{states('input_number.test_number60')}}"

async def test_states_power_with_attributes():
    source_entity = create_source_entity("media_player")

    strategy = FixedStrategy(
        source_entity,
        power=12,
        per_state_power={"media_content_id|Spotify": 5, "media_content_id|Youtube": 10},
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