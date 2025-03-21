from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
)
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import (
    get_test_profile_dir,
    run_powercalc_setup,
)
from tests.conftest import MockEntityWithModel


async def test_infrared_light(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Infrared capable light with several sub profiles
    """
    power_sensor_id = "sensor.test_power"
    light_id = "light.test"
    infrared_brightness_select_id = "select.test_infrared_brightness"
    manufacturer = "LIFX"
    model = "LIFX A19 Night Vision"

    mock_entity_with_model_information(
        light_id,
        manufacturer,
        model,
        capabilities={ATTR_SUPPORTED_COLOR_MODES: [ColorMode.HS, ColorMode.COLOR_TEMP]},
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("infrared_light"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state

    hass.states.async_set(
        light_id,
        STATE_ON,
        {
            ATTR_BRIGHTNESS: 11,
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_COLOR_TEMP_KELVIN: 1663,
        },
    )
    hass.states.async_set(infrared_brightness_select_id, "50%")
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "4.37"

    hass.states.async_set(infrared_brightness_select_id, "25%")
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.59"

    hass.states.async_set(
        light_id,
        STATE_OFF,
    )
    hass.states.async_set(infrared_brightness_select_id, "50%")
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "4.36"
