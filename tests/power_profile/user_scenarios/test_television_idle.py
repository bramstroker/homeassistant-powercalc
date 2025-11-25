from homeassistant.const import CONF_ENTITY_ID, STATE_IDLE, STATE_PLAYING
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CALCULATION_ENABLED_CONDITION, CONF_LINEAR, CONF_MAX_POWER, CONF_MODE, CalculationStrategy
from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_media_player_idle(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/3492
    """

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "media_player.test",
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_CALCULATION_ENABLED_CONDITION: "{{ true }}",
            CONF_LINEAR: {
                CONF_MAX_POWER: 5,
            },
        },
    )

    hass.states.async_set("media_player.test", STATE_PLAYING, {"volume_level": 0.16})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.80"

    hass.states.async_set("media_player.test", STATE_IDLE, {"volume_level": 0.16})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.80"
