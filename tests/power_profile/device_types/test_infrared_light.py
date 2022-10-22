from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.components.light import ColorMode, ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_COLOR_TEMP
from custom_components.test.light import MockLight

from ...common import create_mock_light_entity

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import get_test_profile_dir, run_powercalc_setup_yaml_config


async def test_infrared_light(hass: HomeAssistant):
    """
    Infrared capable light with several sub profiles
    """
    power_sensor_id = "sensor.test_power"
    light_id = "light.test"

    light_mock = MockLight("test")
    light_mock.manufacturer = "LIFX"
    light_mock.model = "LIFX A19 Night Vision"
    light_mock.supported_color_modes = [ColorMode.HS, ColorMode.COLOR_TEMP]

    await create_mock_light_entity(hass, light_mock)

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: light_id,
            CONF_MANUFACTURER: light_mock.manufacturer,
            CONF_MODEL: light_mock.model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("infrared_light"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state

    hass.states.async_set(
        light_id,
        STATE_ON,
        {
            "infrared_brightness": "50%",
            ATTR_BRIGHTNESS: 11,
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_COLOR_TEMP: 601
        }
    )
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "4.37"

    hass.states.async_set(
        light_id,
        STATE_ON,
        {
            "infrared_brightness": "25%",
            ATTR_BRIGHTNESS: 11,
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_COLOR_TEMP: 601
        }
    )
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.59"

