import logging

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry

from custom_components.powercalc.power_profile.model_discovery import (
    get_power_profile,
    is_autoconfigurable,
)
from custom_components.test.light import MockLight

from ..common import create_mock_light_entity


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
        (
            "ikea",
            "IKEA FLOALT LED light panel, dimmable, white spectrum (30x90 cm) (L1528)",
            "ikea",
            "L1528",
        ),
        ("IKEA", "LED1649C5", "ikea", "LED1649C5"),
        (
            "IKEA",
            "TRADFRI LED bulb GU10 400 lumen, dimmable (LED1650R5)",
            "ikea",
            "LED1650R5",
        ),
        (
            "ikea",
            "TRADFRI bulb E14 W op/ch 400lm",
            "ikea",
            "LED1649C5",
        ),
        ("MLI", 45317, "mueller-licht", "45317"),
        ("TP-Link", "KP115(AU)", "tp-link", "KP115"),
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
    """
    Test the autodiscovery lookup from the library by manufacturer and model information
    A given entity_entry is trying to be matched in the library and a PowerProfile instance returned when it is matched
    """
    light_mock = MockLight("testa")
    light_mock.manufacturer = manufacturer
    light_mock.model = model

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.testa")

    power_profile = await get_power_profile(hass, {}, entity_entry)

    assert power_profile.manufacturer == expected_manufacturer
    assert power_profile.model == expected_model


async def test_get_power_profile_empty_manufacturer(
    hass: HomeAssistant, entity_reg: EntityRegistry, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    light_mock = MockLight("test")
    light_mock.manufacturer = ""
    light_mock.model = "some model"

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.test")

    profile = await get_power_profile(hass, {}, entity_entry)
    assert not profile
    assert not caplog.records


async def test_is_autoconfigurable_returns_false(
    hass: HomeAssistant, entity_reg: EntityRegistry
) -> None:
    """
    is_autoconfigurable should return False when the manufacturer / model is not found in the library
    """
    light_mock = MockLight("testa")
    light_mock.manufacturer = "Foo"
    light_mock.model = "Bar"

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.testa")
    assert not await is_autoconfigurable(hass, entity_entry)
