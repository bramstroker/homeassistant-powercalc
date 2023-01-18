import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ColorMode
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import (
    EntityRegistry,
    RegistryEntry,
    RegistryEntryDisabler,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_ENABLE_AUTODISCOVERY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.powercalc.discovery import autodiscover_model
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.test.light import MockLight

from .common import create_mock_light_entity, run_powercalc_setup


@pytest.fixture
def mock_flow_init(hass):
    """Mock hass.config_entries.flow.async_init."""
    with patch.object(
        hass.config_entries.flow, "async_init", return_value=AsyncMock()
    ) as mock_init:
        yield mock_init


async def test_autodiscovery(hass: HomeAssistant, mock_flow_init) -> None:
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

    # Check that two discovery flows have been initialized
    # LightA and LightB should be discovered, LightC not
    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 2
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == "light.testa"
    assert mock_calls[1][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[1][2]["data"][CONF_ENTITY_ID] == "light.testb"

    # Also check if power sensors are created.
    # Currently, we also create them directly, even without the user finishing the discovery flow
    # In the future this behaviour may change.
    assert hass.states.get("sensor.testa_power")
    assert hass.states.get("sensor.testb_power")
    assert not hass.states.get("sensor.testc_power")


async def test_discovery_skipped_when_confirmed_by_user(
    hass: HomeAssistant, mock_flow_init
) -> None:
    light_entity = MockLight("test")
    light_entity.manufacturer = "lidl"
    light_entity.model = "HG06106C"
    await create_mock_light_entity(hass, light_entity)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNIQUE_ID: light_entity.unique_id,
            CONF_NAME: light_entity.name,
            CONF_ENTITY_ID: light_entity.entity_id,
            CONF_MANUFACTURER: light_entity.manufacturer,
            CONF_MODEL: light_entity.model,
        },
        source=SOURCE_INTEGRATION_DISCOVERY,
        unique_id=light_entity.unique_id,
    )
    config_entry.add_to_hass(hass)

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not mock_flow_init.mock_calls


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
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_autodiscovery_skipped_for_lut_with_subprofiles(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Lights which can be autodiscovered and have sub profiles need to de skipped
    User needs to configure this because we cannot know which sub profile to select
    No power sensor should be created and no error should appear in the logs
    """
    caplog.set_level(logging.ERROR)

    light_entity = MockLight("testa")
    light_entity.manufacturer = "Yeelight"
    light_entity.model = "strip6"
    light_entity.supported_color_modes = [ColorMode.COLOR_TEMP, ColorMode.HS]
    await create_mock_light_entity(hass, light_entity)

    await async_setup_component(
        hass, DOMAIN, {DOMAIN: {CONF_ENABLE_AUTODISCOVERY: True}}
    )
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.testa_power")
    assert not caplog.records


async def test_manually_configured_light_overrides_autodiscovered(
    hass: HomeAssistant, mock_flow_init
) -> None:
    light_entity = MockLight("testing")
    light_entity.manufacturer = "signify"
    light_entity.model = "LCA001"
    await create_mock_light_entity(hass, light_entity)

    await run_powercalc_setup(
        hass, {CONF_ENTITY_ID: "light.testing", CONF_FIXED: {CONF_POWER: 25}}, {}
    )

    assert len(mock_flow_init.mock_calls) == 0

    state = hass.states.get("sensor.testing_power")
    assert state
    assert state.state == "25.00"


async def test_config_entry_overrides_autodiscovered(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)

    light_entity = MockLight("testing", unique_id="abcdef")
    light_entity.manufacturer = "signify"
    light_entity.model = "LWA017"
    light_entity.color_mode = ColorMode.BRIGHTNESS
    await create_mock_light_entity(hass, light_entity)

    hass.states.async_set(
        "light.testing",
        STATE_ON,
        {ATTR_BRIGHTNESS: 200, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS},
    )

    await run_powercalc_setup(hass, {}, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testing",
            CONF_ENTITY_ID: "light.testing",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LWA017",
        },
        unique_id="abcdef",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testing_power")
    assert not caplog.records


async def test_autodiscover_skips_disabled_entities(hass: HomeAssistant) -> None:
    """Auto discovery should not consider disabled entities"""
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="some-device-id",
                disabled_by=RegistryEntryDisabler.HASS,
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "light.test": DeviceEntry(
                id="some-device-id", manufacturer="signify", model="LCT010"
            )
        },
    )
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.test_power")


async def test_autodiscover_skips_entities_with_empty_manufacturer(
    hass: HomeAssistant,
) -> None:
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="some-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "light.test": DeviceEntry(
                id="some-device-id", manufacturer="", model="LCT010"
            )
        },
    )
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.test_power")


async def test_load_model_with_slashes(hass: HomeAssistant, entity_reg: EntityRegistry):
    """
    Discovered model with slashes should not be treated as a sub lut profile
    """
    light_mock = MockLight("testa")
    light_mock.manufacturer = "ikea"
    light_mock.model = "TRADFRI bulb E14 W op/ch 400lm"

    await create_mock_light_entity(hass, light_mock)

    entity_entry = entity_reg.async_get("light.testa")

    profile = await get_power_profile(
        hass, {}, await autodiscover_model(hass, entity_entry)
    )
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

    power_profile = await get_power_profile(
        hass, {}, await autodiscover_model(hass, entity_entry)
    )

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

    profile = await get_power_profile(
        hass, {}, await autodiscover_model(hass, entity_entry)
    )
    assert not profile
    assert not caplog.records


async def test_no_power_sensors_are_created_for_ignored_config_entries(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.DEBUG)

    unique_id = "abc"
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id=unique_id,
                platform="light",
                device_id="some-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "some-device-id": DeviceEntry(
                id="some-device-id", manufacturer="Signify", model="LCT010"
            )
        },
    )

    config_entry_unique_id = f"pc_{unique_id}"
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNIQUE_ID: config_entry_unique_id,
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "Signify",
            CONF_MODEL: "LCT010",
        },
        source=SOURCE_IGNORE,
        unique_id=config_entry_unique_id,
    )
    config_entry.add_to_hass(hass)

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.test_power")
    assert "Already setup with discovery, skipping new discovery" in caplog.text
