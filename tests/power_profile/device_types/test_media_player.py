import os

from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.const import STATE_PLAYING, STATE_PAUSED
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import run_powercalc_setup_yaml_config


async def test_media_player(hass: HomeAssistant):
    """
    Test that media player can be setup from profile library
    """
    entity_id = "media_player.nest_mini"
    manufacturer = "Google Inc."
    model = "Google Nest Mini"

    mock_registry(
        hass,
        {
            entity_id: RegistryEntry(
                entity_id=entity_id,
                unique_id="1234",
                platform="switch",
                device_id="nest-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "nest-device": DeviceEntry(
                id="nest-device-id", manufacturer=manufacturer, model=model
            )
        },
    )

    power_sensor_id = "sensor.nest_mini_power"

    await run_powercalc_setup_yaml_config(
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

    hass.states.async_set(entity_id, STATE_PLAYING, {"volume_level": 0.20, "is_volume_muted": False})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.04"

    hass.states.async_set(entity_id, STATE_PAUSED, {"volume_level": 0.20, "is_volume_muted": False})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.65"

    hass.states.async_set(entity_id, STATE_PLAYING, {"volume_level": 0.20, "is_volume_muted": True})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.01"

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.65"


def get_test_profile_dir(sub_dir: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), "../../testing_config/powercalc_profiles", sub_dir
    )
