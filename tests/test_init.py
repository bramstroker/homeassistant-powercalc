from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.powercalc.const import CONF_ENABLE_AUTODISCOVERY, DOMAIN
from custom_components.test.light import MockLight

from .common import create_mock_light_entity


async def test_autodiscovery(hass: HomeAssistant):
    """Test that models are automatically discovered and power sensors created"""

    lighta = MockLight("testa")
    lighta.manufacturer = "lidl"
    lighta.model = "HG06106C"

    lightb = MockLight("testb")
    lightb.manufacturer = "signify"
    lightb.model = "LCA001"

    lightc = MockLight("testc")
    lightc.manufacturer = "lidl"
    lightc.model = "NONEXISTING"
    await create_mock_light_entity(hass, [lighta, lightb, lightc])

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testa_power")
    assert hass.states.get("sensor.testb_power")
    assert not hass.states.get("sensor.testc_power")


async def test_autodiscovery_disabled(hass: HomeAssistant):
    """Test that power sensors are not automatically added when auto discovery is disabled"""

    light_entity = MockLight("testa")
    light_entity.manufacturer = "lidl"
    light_entity.model = "HG06106C"
    await create_mock_light_entity(hass, light_entity)

    await async_setup_component(
        hass, DOMAIN, {DOMAIN: {CONF_ENABLE_AUTODISCOVERY: False}}
    )
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.testa_power")
