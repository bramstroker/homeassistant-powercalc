from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_PAUSED, STATE_PLAYING
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODEL,
    CONF_STANDBY_POWER,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_media_player(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that media player can be setup from profile library
    """
    entity_id = "media_player.nest_mini"
    manufacturer = "Google Inc."
    model = "Google Nest Mini"

    mock_entity_with_model_information(
        entity_id=entity_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.nest_mini_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("media_player"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(
        entity_id,
        STATE_PLAYING,
        {"volume_level": 0.20, "is_volume_muted": False},
    )
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.04"

    hass.states.async_set(
        entity_id,
        STATE_PAUSED,
        {"volume_level": 0.20, "is_volume_muted": False},
    )
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.65"

    hass.states.async_set(
        entity_id,
        STATE_PLAYING,
        {"volume_level": 0.20, "is_volume_muted": True},
    )
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.01"

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.65"


async def test_media_player_manual_configuration(hass: HomeAssistant) -> None:
    entity_id = "media_player.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_STANDBY_POWER: 2,
            CONF_LINEAR: {
                CONF_MIN_POWER: 5,
                CONF_MAX_POWER: 50,
            },
        },
    )

    hass.states.async_set(
        entity_id,
        STATE_PLAYING,
        {"volume_level": 0.20, "is_volume_muted": False},
    )

    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "14.00"

    hass.states.async_set(
        entity_id,
        STATE_PAUSED,
    )

    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.00"
