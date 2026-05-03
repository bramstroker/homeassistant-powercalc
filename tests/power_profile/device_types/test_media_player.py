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
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup, set_states
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

    assert_entity_state(hass, power_sensor_id, "unavailable")

    await set_states(
        hass,
        [
            (
                entity_id,
                STATE_PLAYING,
                {"volume_level": 0.20, "is_volume_muted": False},
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "2.04")

    await set_states(
        hass,
        [
            (
                entity_id,
                STATE_PAUSED,
                {"volume_level": 0.20, "is_volume_muted": False},
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "1.65")

    await set_states(
        hass,
        [
            (
                entity_id,
                STATE_PLAYING,
                {"volume_level": 0.20, "is_volume_muted": True},
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "2.01")

    await set_states(hass, [(entity_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "1.65")


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

    await set_states(
        hass,
        [
            (
                entity_id,
                STATE_PLAYING,
                {"volume_level": 0.20, "is_volume_muted": False},
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "14.00")

    await set_states(
        hass,
        [
            (
                entity_id,
                STATE_PAUSED,
            ),
        ],
    )
    assert_entity_state(hass, power_sensor_id, "2.00")
