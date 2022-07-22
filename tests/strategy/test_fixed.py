from homeassistant.setup import async_setup_component
from homeassistant.core import State
from homeassistant.const import (
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from custom_components.powercalc.common import SourceEntity
from homeassistant.components import (
    input_number
)

from custom_components.powercalc.strategy.fixed import FixedStrategy

async def test_simple_power():
    source_entity = SourceEntity(
        "test",
        "switch.test",
        "switch"
    )
    strategy = FixedStrategy(source_entity, power=50, per_state_power=None)
    assert 50 == await strategy.calculate(State("switch.test", STATE_ON))

async def test_template_power(hass: HomeAssistant):
    assert await async_setup_component(
        hass, input_number.DOMAIN, {"input_number": {"test": {"min": "0", "max": "100", "initial": "42"}}}
    )
    
    await hass.async_block_till_done()

    source_entity = SourceEntity(
        "test",
        "switch.test",
        "switch"
    )
    strategy = FixedStrategy(
        source_entity,
        power=Template("{{states('input_number.test')}}", hass),
        per_state_power=None)

    assert 42 == await strategy.calculate(State("switch.test", STATE_ON))

async def test_states_power(hass: HomeAssistant):
    entity_id = "media_player.sonos_living"
    source_entity = SourceEntity(
        "sonos_living",
        entity_id,
        "media_player"
    )
    strategy = FixedStrategy(
        source_entity,
        power=20,
        per_state_power={
            "playing": 8.3,
            "paused": 2.25,
            "idle": 1.5
        }
    )
    assert 8.3 == await strategy.calculate(State(entity_id, "playing"))
    assert 2.25 == await strategy.calculate(State(entity_id, "paused"))
    assert 1.5 == await strategy.calculate(State(entity_id, "idle"))
    assert 20 == await strategy.calculate(State(entity_id, "whatever"))

async def test_states_power_with_attributes():
    entity_id = "media_player.sonos_living"
    source_entity = SourceEntity(
        "sonos_living",
        entity_id,
        "media_player"
    )
    strategy = FixedStrategy(
        source_entity,
        power=12,
        per_state_power={
            "media_content_id|Spotify": 5,
            "media_content_id|Youtube": 10
        }
    )

    assert 5 == await strategy.calculate(State(entity_id, "playing", {"media_content_id": "Spotify"}))
    assert 10 == await strategy.calculate(State(entity_id, "playing", {"media_content_id": "Youtube"}))
    assert 12 == await strategy.calculate(State(entity_id, "playing", {"media_content_id": "Netflix"}))