import logging
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
)
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_SOURCE, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import SERVICE_UPDATE_LIBRARY, DeviceType, DiscoveryManager
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import (
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_FACTOR,
    CONF_SENSOR_TYPE,
    CONF_VOLTAGE,
    CONF_WLED,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SensorType,
)
from custom_components.powercalc.discovery import get_power_profile_by_source_entity
from custom_components.powercalc.power_profile.library import ModelInfo
from custom_components.test.light import MockLight

from .common import create_mock_light_entity, get_test_config_dir, run_powercalc_setup
from .conftest import MockEntityWithModel

DEFAULT_UNIQUE_ID = "7c009ef6829f"


async def test_autodiscovery(hass: HomeAssistant, mock_flow_init: AsyncMock) -> None:
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

    await run_powercalc_setup(hass, {})

    # Check that two discovery flows have been initialized
    # LightA and LightB should be discovered, LightC not
    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 2
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == "light.testa"
    assert mock_calls[1][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[1][2]["data"][CONF_ENTITY_ID] == "light.testb"


async def test_discovery_skipped_when_confirmed_by_user(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        "light.test",
        "lidl",
        "HG06106C",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_NAME: "",
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "lidl",
            CONF_MODEL: "HG06106C",
        },
        source=SOURCE_INTEGRATION_DISCOVERY,
        unique_id=DEFAULT_UNIQUE_ID,
    )
    config_entry.add_to_hass(hass)

    await run_powercalc_setup(hass, {})

    assert not mock_flow_init.mock_calls


async def test_autodiscovery_disabled(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Test that power sensors are not automatically added when auto discovery is disabled"""

    mock_entity_with_model_information("light.testa", "lidl", "HG06106C")

    await run_powercalc_setup(hass, {}, {CONF_ENABLE_AUTODISCOVERY: False})

    assert not hass.states.get("sensor.testa_power")
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_autodiscovery_skipped_for_lut_with_subprofiles(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Lights which can be autodiscovered and have sub profiles need to be skipped
    User needs to configure this because we cannot know which sub profile to select
    No power sensor should be created and no error should appear in the logs
    """
    caplog.set_level(logging.ERROR)

    mock_entity_with_model_information(
        "light.testa",
        "Yeelight",
        "strip6",
        capabilities={ATTR_SUPPORTED_COLOR_MODES: [ColorMode.COLOR_TEMP, ColorMode.HS]},
    )

    await run_powercalc_setup(hass, {}, {CONF_ENABLE_AUTODISCOVERY: True})

    assert not hass.states.get("sensor.testa_power")
    assert not caplog.records


async def test_manually_configured_light_overrides_autodiscovered(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.testing", "signify", "LCA001")
    hass.states.async_set("light.testing", STATE_ON)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "light.testing", CONF_FIXED: {CONF_POWER: 25}},
        {},
    )

    assert len(mock_flow_init.mock_calls) == 0

    state = hass.states.get("sensor.testing_power")
    assert state
    assert state.state == "25.00"


async def test_config_entry_overrides_autodiscovered(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    caplog.set_level(logging.ERROR)

    mock_entity_with_model_information(
        "light.testing",
        "signify",
        "LWA017",
        unique_id="abcdef",
    )

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


async def test_autodiscover_skips_disabled_entities(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Auto discovery should not consider disabled entities"""
    mock_entity_with_model_information(
        "light.test",
        "signify",
        "LCT010",
        disabled_by=er.RegistryEntryDisabler.HASS,
    )

    await run_powercalc_setup(hass, {})

    assert not hass.states.get("sensor.test_power")


async def test_autodiscover_skips_entities_with_empty_manufacturer(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test", "", "LCT010")

    await run_powercalc_setup(hass, {})

    assert not hass.states.get("sensor.test_power")


async def test_autodiscover_skips_diagnostics_entities(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Auto discovery should not consider entities with entity_category diagnostic"""

    mock_entity_with_model_information(
        "switch.test",
        "Shelly",
        "Shelly Plug S",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    await run_powercalc_setup(hass, {})

    assert not hass.states.get("sensor.test_device_power")


async def test_autodiscover_skips_printer_ink(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    """Auto discovery should not consider printer entities with ink in the name"""

    mock_entity_with_model_information(
        "sensor.epson_et_3760_series_black_ink",
        "EPSON",
        "ET-3760 Series",
        unit_of_measurement="%",
    )

    await run_powercalc_setup(hass, {})

    assert len(mock_flow_init.mock_calls) == 0


async def test_autodiscover_skips_unsupported_domains(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        "device_tracker.test",
        "signify",
        "LCT010",
    )

    await run_powercalc_setup(hass, {})

    assert not hass.states.get("sensor.test_power")


async def test_autodiscover_continues_when_one_entity_fails(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auto discovery should continue when one entity fails to load model information"""

    caplog.set_level(logging.ERROR)

    mock_device_registry(
        hass,
        {
            "signify-device": DeviceEntry(
                id="signify-device",
                manufacturer="signify",
                model="LCT010",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "light.test1": RegistryEntry(
                entity_id="light.test1",
                unique_id="1234",
                platform="light",
                device_id="signify-device",
            ),
            "light.test2": RegistryEntry(
                entity_id="light.test2",
                unique_id="1235",
                platform="light",
                device_id="signify-device",
            ),
        },
    )
    with patch("custom_components.powercalc.power_profile.library.ProfileLibrary.find_models", new_callable=AsyncMock) as mock_find_models:
        mock_find_models.side_effect = [Exception("Test exception"), {ModelInfo("signify", "LCT010")}]
        await run_powercalc_setup(hass, {})
        assert "Error during entity discovery" in caplog.text


async def test_exclude_device_types(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    """Test that entities with excluded device types are not considered for discovery"""

    mock_device_registry(
        hass,
        {
            "switch-device": DeviceEntry(
                id="switch-device",
                manufacturer="shelly",
                model="SHPLG-S",
            ),
            "light-device": DeviceEntry(
                id="light-device",
                manufacturer="signify",
                model="LCT010",
            ),
            "cover-device": DeviceEntry(
                id="cover-device",
                manufacturer="eq-3",
                model="HmIP-FROLL",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1111",
                platform="hue",
                device_id="light-device",
            ),
            "switch.test": RegistryEntry(
                entity_id="switch.test",
                unique_id="2222",
                platform="shelly",
                device_id="switch-device",
            ),
            "cover.test": RegistryEntry(
                entity_id="cover.test",
                unique_id="3333",
                platform="shelly",
                device_id="cover-device",
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES: [
                DeviceType.SMART_SWITCH,
                DeviceType.COVER,
            ],
        },
    )

    assert len(mock_flow_init.mock_calls) == 1


async def test_load_model_with_slashes(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Discovered model with slashes should not be treated as a sub lut profile
    """
    mock_entity_with_model_information(
        "light.testa",
        "ikea",
        "TRADFRI bulb E14 W op/ch 400lm",
    )

    source_entity = await create_source_entity("light.testa", hass)
    profile = await get_power_profile_by_source_entity(hass, source_entity)
    assert profile
    assert profile.manufacturer == "ikea"
    assert profile.model == "LED1649C5"


@pytest.mark.parametrize(
    "entity_id,model_info,expected_manufacturer,expected_model",
    [
        (
            "light.test",
            ModelInfo("ikea", "IKEA FLOALT LED light panel, dimmable, white spectrum (30x90 cm) (L1528)"),
            "ikea",
            "L1528",
        ),
        (
            "light.test",
            ModelInfo("IKEA", "LED1649C5"),
            "ikea",
            "LED1649C5",
        ),
        (
            "light.test",
            ModelInfo("IKEA", "TRADFRI LED bulb GU10 400 lumen, dimmable (LED1650R5)"),
            "ikea",
            "LED1650R5",
        ),
        (
            "light.test",
            ModelInfo("ikea", "TRADFRI bulb E14 W op/ch 400lm"),
            "ikea",
            "LED1649C5",
        ),
        (
            "light.test",
            ModelInfo("MLI", "45317"),
            "mueller-licht",
            "45317",
        ),
        (
            "switch.test",
            ModelInfo("TP-Link", "KP115(AU)"),
            "tp-link",
            "KP115",
        ),
        (
            "media_player.test",
            ModelInfo("Apple", "HomePod (gen 2)"),
            "apple",
            "MQJ83",
        ),
        (
            "light.test",
            ModelInfo("IKEA", "bladiebla", "LED1649C5"),
            "ikea",
            "LED1649C5",
        ),
        (
            "sensor.test",
            ModelInfo("Signify Netherlands B.V.", "LLC020"),
            None,
            None,
        ),
    ],
)
async def test_discover_entity(
    hass: HomeAssistant,
    entity_id: str,
    model_info: ModelInfo,
    expected_manufacturer: str | None,
    expected_model: str | None,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test the autodiscovery lookup from the library by manufacturer and model information
    A given entity_entry is trying to be matched in the library and a PowerProfile instance returned when it is matched
    """
    mock_entity_with_model_information(entity_id, model_info.manufacturer, model_info.model, model_info.model_id)

    source_entity = await create_source_entity(entity_id, hass)
    power_profile = await get_power_profile_by_source_entity(hass, source_entity)

    if not expected_manufacturer:
        assert not power_profile
        return

    assert power_profile.manufacturer == expected_manufacturer
    assert power_profile.model == expected_model


async def test_same_entity_is_not_discovered_twice(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
        title="Test",
        source=SOURCE_INTEGRATION_DISCOVERY,
    )
    config_entry.add_to_hass(hass)

    mock_entity_with_model_information("light.test", "signify", "LCT010")

    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 0


async def test_wled_not_discovered_twice(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pc_a848face92cd",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "WLED",
            CONF_MODE: "wled",
            CONF_MODEL: "FOSS",
            CONF_NAME: "Ledstrip TV boven",
            CONF_UNIQUE_ID: "pc_a848face92cd",
            CONF_WLED: {
                CONF_POWER_FACTOR: 0.9,
                CONF_VOLTAGE: 5.0,
            },
        },
        title="Test",
        source=SOURCE_INTEGRATION_DISCOVERY,
    )
    config_entry.add_to_hass(hass)

    mock_entity_with_model_information("light.test", "WLED", "FOSS")

    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 0


async def test_govee_segment_lights_skipped(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    """
    Govee segment lights should be skipped
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2834
    """
    mock_device_registry(
        hass,
        {
            "govee-device": DeviceEntry(
                id="govee-device",
                manufacturer="Govee",
                model="H6076",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "light.floor_lamp_livingroom": RegistryEntry(
                entity_id="light.floor_lamp_livingroom",
                unique_id="gv2mqtt-F23DD0C844866B65",
                platform="mqtt",
                device_id="govee-device",
            ),
            "light.floor_lamp_livingroom_segment_001": RegistryEntry(
                entity_id="light.floor_lamp_livingroom_segment_001",
                unique_id="gv2mqtt-F23DD0C844866B65-0",
                platform="mqtt",
                device_id="govee-device",
            ),
            "light.floor_lamp_livingroom_segment_002": RegistryEntry(
                entity_id="light.floor_lamp_livingroom_segment_002",
                unique_id="gv2mqtt-F23DD0C844866B65-1",
                platform="mqtt",
                device_id="govee-device",
            ),
            "light.floor_lamp_livingroom_segment_003": RegistryEntry(
                entity_id="light.floor_lamp_livingroom_segment_003",
                unique_id="gv2mqtt-F23DD0C844866B65-2",
                platform="mqtt",
                device_id="govee-device",
            ),
        },
    )

    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1


async def test_get_power_profile_empty_manufacturer(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    caplog.set_level(logging.ERROR)

    mock_entity_with_model_information("light.test", "", "some model")

    source_entity = await create_source_entity("light.test", hass)
    profile = await get_power_profile_by_source_entity(hass, source_entity)

    assert not profile
    assert not caplog.records


async def test_no_power_sensors_are_created_for_ignored_config_entries(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    caplog.set_level(logging.DEBUG)

    unique_id = "abc"
    mock_entity_with_model_information(
        "light.test",
        "Signify",
        "LCT010",
        unique_id=unique_id,
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

    await run_powercalc_setup(hass, {})

    assert not hass.states.get("sensor.test_power")
    assert "Already setup with discovery, skipping" in caplog.text


@pytest.mark.parametrize(
    "entity_entry,device_entry,model_info",
    [
        (
            RegistryEntry(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
            ),
            None,
            None,
        ),
        (
            RegistryEntry(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            DeviceEntry(id="a", manufacturer="foo", model="bar"),
            ModelInfo("foo", "bar", None),
        ),
        (
            RegistryEntry(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            DeviceEntry(id="b", manufacturer="foo", model="bar"),
            None,
        ),
        (
            RegistryEntry(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            DeviceEntry(id="a", manufacturer="foo", model="bar", model_id="barry"),
            ModelInfo("foo", "bar", "barry"),
        ),
    ],
)
async def test_get_model_information(
    hass: HomeAssistant,
    entity_entry: RegistryEntry,
    device_entry: DeviceEntry | None,
    model_info: ModelInfo | None,
) -> None:
    if device_entry:
        mock_device_registry(hass, {str(device_entry.id): device_entry})
    mock_registry(hass, {str(entity_entry.id): entity_entry})
    discovery_manager = DiscoveryManager(hass, {})
    assert await discovery_manager.get_model_information_from_entity(entity_entry) == model_info


async def test_interval_based_rediscovery(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    mock_entity_with_model_information("light.test", "signify", "LCT010")

    await run_powercalc_setup(hass, {}, {CONF_ENABLE_AUTODISCOVERY: True})

    async_fire_time_changed(hass, dt.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done(True)

    async_fire_time_changed(hass, dt.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done(True)

    assert len([record for record in caplog.records if "Start auto discovery" in record.message]) == 3


async def test_update_profile_service(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    mock_entity_with_model_information("light.test", "signify", "LCT010")

    await run_powercalc_setup(hass, {})

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_LIBRARY,
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len([record for record in caplog.records if "Start auto discovery" in record.message]) == 2


async def test_discovery_by_device(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    hass.config.config_dir = get_test_config_dir()

    mock_device_registry(
        hass,
        {
            "youless-device": DeviceEntry(
                id="ABC123",
                manufacturer="test",
                model="discovery_type_device",
            ),
        },
    )

    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert mock_calls[0][1] == (DOMAIN,)
    assert mock_calls[0][2]["context"] == {CONF_SOURCE: SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == DUMMY_ENTITY_ID
    assert mock_calls[0][2]["data"][CONF_MANUFACTURER] == "test"
    assert mock_calls[0][2]["data"][CONF_MODEL] == "discovery_type_device"
    assert mock_calls[0][2]["data"][CONF_UNIQUE_ID] == "pc_ABC123"
    assert len(mock_calls) == 1


async def test_powercalc_sensors_are_ignored_for_discovery(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """Powercalc sensors should not be considered for discovery"""
    hass.config.config_dir = get_test_config_dir()

    mock_device_registry(
        hass,
        {
            "my-device": DeviceEntry(
                id="my-device",
                manufacturer="test",
                model="generic-iot",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "sensor.test_powercalc": RegistryEntry(
                entity_id="sensor.test_powercalc",
                unique_id="1111",
                platform="powercalc",
                device_id="my-device",
            ),
            "sensor.test_other": RegistryEntry(
                entity_id="sensor.test_other",
                unique_id="2222",
                platform="other-platform",
                device_id="my-device",
            ),
        },
    )

    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1


@pytest.mark.parametrize(
    "entity_entries,expected_entities",
    [
        (
            [
                RegistryEntry(
                    entity_id="switch.test",
                    unique_id="1111",
                    platform="hue",
                    device_id="hue-device",
                ),
            ],
            ["switch.test"],
        ),
        # Entity domains that are not supported must be ignored
        (
            [
                RegistryEntry(
                    entity_id="scene.test",
                    unique_id="1111",
                    platform="hue",
                    device_id="hue-device",
                ),
                RegistryEntry(
                    entity_id="event.test",
                    unique_id="2222",
                    platform="hue",
                    device_id="hue-device",
                ),
            ],
            [],
        ),
        # Powercalc sensors should not be considered for discovery
        (
            [
                RegistryEntry(
                    entity_id="sensor.test",
                    unique_id="1111",
                    platform="powercalc",
                    device_id="some-device",
                ),
            ],
            [],
        ),
        # SwitchAsX entities should be ignored
        (
            [
                RegistryEntry(
                    entity_id="switch.test",
                    unique_id="1111",
                    platform="mqtt",
                    device_id="some-device",
                ),
                RegistryEntry(
                    entity_id="light.test",
                    unique_id="2222",
                    platform="switch_as_x",
                    device_id="some-device",
                ),
            ],
            ["switch.test"],
        ),
    ],
)
async def test_get_entities(hass: HomeAssistant, entity_entries: list[RegistryEntry], expected_entities: list[str]) -> None:
    mock_registry(hass, {entity_entry.entity_id: entity_entry for entity_entry in entity_entries})
    discovery_manager = DiscoveryManager(hass, {})
    entity_ids = [entity.entity_id for entity in await discovery_manager.get_entities()]
    assert entity_ids == expected_entities
