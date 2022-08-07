import pytest

from homeassistant.core import HomeAssistant

from homeassistant.helpers.entity_registry import EntityRegistry
from custom_components.test.light import MockLight
from ..common import create_mock_light_entity

from custom_components.powercalc.const import DOMAIN
from custom_components.powercalc.power_profile.model_discovery import (
    get_power_profile,
    autodiscover_model
)

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

@pytest.mark.parametrize(
    "manufacturer,model,expected_manufacturer,expected_model",
    [
        ("ikea", "IKEA FLOALT LED light panel, dimmable, white spectrum (30x90 cm) (L1528)", "ikea", "L1528"),
        ("IKEA", "LED1649C5", "IKEA of Sweden", "LED1649C5"),
        ("IKEA", "TRADFRI LED bulb GU10 400 lumen, dimmable (LED1650R5)", "IKEA of Sweden", "LED1650R5"),
        ("ikea", "TRADFRI bulb E14 W op/ch 400lm", "ikea", "TRADFRI bulb E14 W op#slash#ch 400lm"),
        ("MLI", "45317", "Müller Licht", "45317")
    ],
)
async def test_autodiscover_model_from_entity_entry(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    manufacturer: str,
    model: str,
    expected_manufacturer: str,
    expected_model: str,
):
    light_mock = MockLight("testa")
    light_mock.manufacturer = manufacturer
    light_mock.model = model

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.testa")

    model_info = await autodiscover_model(hass, entity_entry)

    assert model_info.manufacturer == expected_manufacturer
    assert model_info.model == expected_model