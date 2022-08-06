from homeassistant.core import HomeAssistant

from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.setup import async_setup_component
from custom_components.test.light import MockLight
from ..common import create_mock_light_entity

from custom_components.powercalc.const import DOMAIN
from custom_components.powercalc.power_profile.model_discovery import get_power_profile

async def test_load_model_with_slashes(hass: HomeAssistant, entity_reg: EntityRegistry):
    """
    Discovered model with slashes should not be treated as a sub lut profile
    """
    light_mock = MockLight("testa")
    light_mock.manufacturer = "ikea"
    light_mock.model = "TRADFRI bulb E14 W op/ch 400lm"

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.testa")

    profile = await get_power_profile(hass, {}, entity_entry)
    assert profile
    assert profile.manufacturer == light_mock.manufacturer
    assert profile.model == "LED1649C5"