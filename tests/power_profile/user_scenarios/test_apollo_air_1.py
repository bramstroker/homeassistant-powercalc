from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_VARIABLES
from custom_components.powercalc.helpers import get_library_path
from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_rgb_light_changes_update_power(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """The AIR-1 profile must render its block template and track RGB light changes."""
    source_entity = "sensor.air_1_co2"
    light_entity = "light.air_1_rgb_light"
    power_entity = "sensor.air_1_co2_power"

    await set_states(hass, [(source_entity, "500"), (light_entity, STATE_OFF)])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: source_entity,
            CONF_CUSTOM_MODEL_DIRECTORY: get_library_path("apollo automation/AIR-1"),
            CONF_VARIABLES: {"rgb_light": light_entity},
        },
    )

    assert_entity_state(hass, power_entity, "1.15")

    await set_states(
        hass,
        [(light_entity, STATE_ON, {ATTR_BRIGHTNESS: 255, ATTR_RGB_COLOR: [255, 255, 255]})],
    )
    assert_entity_state(hass, power_entity, "1.81")

    await set_states(
        hass,
        [(light_entity, STATE_ON, {ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: [255, 255, 255]})],
    )
    assert_entity_state(hass, power_entity, "1.32")

    await set_states(
        hass,
        [(light_entity, STATE_ON, {ATTR_BRIGHTNESS: 255, ATTR_RGB_COLOR: [255, 0, 0]})],
    )
    assert_entity_state(hass, power_entity, "1.37")

    await set_states(hass, [(light_entity, STATE_OFF)])
    assert_entity_state(hass, power_entity, "1.15")
    assert "Could not convert value" not in caplog.text
