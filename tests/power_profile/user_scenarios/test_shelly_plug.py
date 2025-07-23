from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_shelly_plug_auto_sub_profile(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/3370#issuecomment-3102005428
    """
    mock_entity_with_model_information(
        "switch.test",
        "shelly",
        "Shelly Plug S",
        platform="shelly",
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
        },
    )

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_device_power").state == "0.80"
