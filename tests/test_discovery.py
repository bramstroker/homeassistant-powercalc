from datetime import timedelta
import logging
from typing import Any
from unittest.mock import AsyncMock, patch
import uuid

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
)
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENABLED, CONF_ENTITY_ID, CONF_NAME, CONF_SOURCE, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import RegistryEntry
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import (
    CONF_DISCOVERY,
    CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
    SERVICE_UPDATE_LIBRARY,
    DeviceType,
    DiscoveryManager,
)
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import (
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
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
from custom_components.powercalc.discovery import (
    DiscoveryStatus,
    get_power_profile_by_source_device,
    get_power_profile_by_source_entity,
)
from custom_components.powercalc.power_profile.library import ModelInfo

from .common import (
    assert_entity_state,
    async_advance_time,
    build_device_entry,
    create_mock_config_entry,
    mock_device,
    mock_device_with_entities,
    mock_devices,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)
from .config_flow.test_global_configuration import create_mock_global_config_entry

DEFAULT_UNIQUE_ID = "7c009ef6829f"
LIGHT_ATTRIBUTES = {ATTR_SUPPORTED_COLOR_MODES: [ColorMode.BRIGHTNESS], ATTR_COLOR_MODE: ColorMode.BRIGHTNESS}


async def test_autodiscovery(hass: HomeAssistant, mock_flow_init: AsyncMock) -> None:
    """Test that models are automatically discovered and power sensors created"""

    mock_devices(
        hass,
        {
            "testa-device": {"manufacturer": "lidl", "model": "HG06106C"},
            "testb-device": {"manufacturer": "signify", "model": "LCA001"},
            "testc-device": {"manufacturer": "lidl", "model": "NONEXISTING"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.testa": {"device_id": "testa-device"},
            "light.testb": {"device_id": "testb-device"},
            "light.testc": {"device_id": "testc-device"},
        },
    )
    await set_states(
        hass,
        [(f"light.test{suffix}", STATE_ON, LIGHT_ATTRIBUTES) for suffix in ("a", "b", "c")],
    )

    await run_powercalc_setup(hass)

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
) -> None:
    mock_device_with_entities(
        hass,
        "light.test",
        "lidl",
        "HG06106C",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_NAME: "",
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "lidl",
            CONF_MODEL: "HG06106C",
        },
        unique_id=DEFAULT_UNIQUE_ID,
        source=SOURCE_INTEGRATION_DISCOVERY,
        setup=False,
    )

    await run_powercalc_setup(hass)

    assert not mock_flow_init.mock_calls


async def test_autodiscovery_disabled(
    hass: HomeAssistant,
) -> None:
    """Test that power sensors are not automatically added when auto discovery is disabled"""

    mock_device_with_entities(hass, "light.testa", "lidl", "HG06106C")

    await run_powercalc_setup(hass, {}, {CONF_DISCOVERY: {CONF_ENABLED: False}})

    assert not hass.states.get("sensor.testa_power")
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_autodiscovery_skipped_for_lut_with_subprofiles(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Lights which can be autodiscovered and have sub profiles need to be skipped
    User needs to configure this because we cannot know which sub profile to select
    No power sensor should be created and no error should appear in the logs
    """
    caplog.set_level(logging.ERROR)

    mock_device_with_entities(
        hass,
        "light.testa",
        "Yeelight",
        "strip6",
        capabilities={ATTR_SUPPORTED_COLOR_MODES: [ColorMode.COLOR_TEMP, ColorMode.HS]},
    )

    await run_powercalc_setup(hass)

    assert not hass.states.get("sensor.testa_power")
    assert not caplog.records


async def test_manually_configured_light_overrides_autodiscovered(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    mock_device_with_entities(hass, "light.testing", "signify", "LCA001")
    await set_states(hass, [("light.testing", STATE_ON)])
    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "light.testing", CONF_FIXED: {CONF_POWER: 25}},
    )

    assert len(mock_flow_init.mock_calls) == 0

    assert_entity_state(hass, "sensor.testing_power", "25.00")


async def test_config_entry_overrides_autodiscovered(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    mock_device_with_entities(
        hass,
        "light.testing",
        "signify",
        "LWA017",
        unique_id="abcdef",
    )

    await set_states(
        hass,
        [
            (
                "light.testing",
                STATE_ON,
                {ATTR_BRIGHTNESS: 200, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS},
            ),
        ],
    )
    await run_powercalc_setup(hass)

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testing",
            CONF_ENTITY_ID: "light.testing",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LWA017",
        },
    )

    assert hass.states.get("sensor.testing_power")
    assert not caplog.records


@pytest.mark.parametrize(
    "entity_id,manufacturer,model,extra_kwargs",
    [
        # Test case for disabled entities
        (
            "light.test",
            "signify",
            "LCT010",
            {"disabled_by": er.RegistryEntryDisabler.HASS},
        ),
        # Test case for entities with empty manufacturer
        (
            "light.test",
            "",
            "LCT010",
            {},
        ),
        # Test case for diagnostic entities
        (
            "switch.test",
            "Shelly",
            "Shelly Plug S",
            {"entity_category": EntityCategory.DIAGNOSTIC},
        ),
        # Test case for printer ink entities
        (
            "sensor.epson_et_3760_series_black_ink",
            "EPSON",
            "ET-3760 Series",
            {"unit_of_measurement": "%"},
        ),
        # Test case for unsupported domains
        (
            "device_tracker.test",
            "signify",
            "LCT010",
            {},
        ),
        # Test case for unknown device type
        (
            "vacuum.test",
            "test",
            "unknown_device_type",
            {},
        ),
    ],
)
async def test_autodiscover_skipped(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
    entity_id: str,
    manufacturer: str,
    model: str,
    extra_kwargs: dict,
) -> None:
    """Test that auto discovery skips entities based on various conditions."""
    mock_device_with_entities(
        hass,
        entity_id,
        manufacturer,
        model,
        **extra_kwargs,
    )

    await run_powercalc_setup(hass)

    assert len(mock_flow_init.mock_calls) == 0


async def test_autodiscover_continues_when_one_entity_fails(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auto discovery should continue when one entity fails to load model information"""

    caplog.set_level(logging.ERROR)

    mock_device_with_entities(hass, ["light.test1", "light.test2"])
    with patch(
        "custom_components.powercalc.power_profile.library.ProfileLibrary.find_models",
        new_callable=AsyncMock,
    ) as mock_find_models:
        mock_find_models.side_effect = [Exception("Test exception"), {ModelInfo("signify", "LCT010")}]
        await run_powercalc_setup(hass)
        assert "Error during entity discovery" in caplog.text


async def test_exclude_device_types(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """Test that entities with excluded device types are not considered for discovery"""

    mock_devices(
        hass,
        {
            "switch-device": {"manufacturer": "shelly", "model": "SHPLG-S"},
            "light-device": {"manufacturer": "signify", "model": "LCT010"},
            "cover-device": {"manufacturer": "eq-3", "model": "HmIP-FROLL"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.test": {"platform": "hue", "device_id": "light-device"},
            "switch.test": {"platform": "shelly", "device_id": "switch-device"},
            "cover.test": {"platform": "shelly", "device_id": "cover-device"},
        },
    )

    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY: {
                CONF_EXCLUDE_DEVICE_TYPES: [
                    DeviceType.SMART_SWITCH,
                    DeviceType.COVER,
                ],
            },
        },
    )

    assert len(mock_flow_init.mock_calls) == 1


async def test_exclude_self_usage(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """Test that entities with excluded device types are not considered for discovery"""
    mock_device_with_entities(
        hass,
        "switch.test",
        "test",
        "smart_switch_with_pm_new",
    )

    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY: {
                CONF_EXCLUDE_SELF_USAGE: True,
            },
        },
    )

    assert len(mock_flow_init.mock_calls) == 0


async def test_load_model_with_slashes(
    hass: HomeAssistant,
) -> None:
    """
    Discovered model with slashes should not be treated as a sub lut profile
    """
    mock_device_with_entities(
        hass,
        "light.testa",
        "ikea",
        "TRADFRI bulb E14 W op/ch 400lm",
    )

    source_entity = create_source_entity("light.testa", hass)
    profile = await get_power_profile_by_source_entity(hass, source_entity)
    assert profile
    assert profile.manufacturer == "ikea"
    assert profile.model == "LED1649C5"


async def test_get_power_profile_by_source_device_returns_none_without_required_entries(hass: HomeAssistant) -> None:
    device_entry = mock_device(hass, model="discovery_type_device")
    mock_entities_in_registry(
        hass,
        {
            "sensor.test": {"unique_id": "test-entity", "device_id": device_entry.id, "platform": "test"},
        },
    )

    source_entity = create_source_entity("sensor.test", hass)

    assert await get_power_profile_by_source_device(hass, source_entity._replace(device_entry=None)) is None
    assert await get_power_profile_by_source_device(hass, source_entity._replace(entity_entry=None)) is None


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
) -> None:
    """
    Test the autodiscovery lookup from the library by manufacturer and model information
    A given entity_entry is trying to be matched in the library and a PowerProfile instance returned when it is matched
    """
    mock_device_with_entities(hass, entity_id, model_info.manufacturer, model_info.model, model_info.model_id)

    source_entity = create_source_entity(entity_id, hass)
    power_profile = await get_power_profile_by_source_entity(hass, source_entity)

    if not expected_manufacturer:
        assert not power_profile
        return

    assert power_profile.manufacturer == expected_manufacturer
    assert power_profile.model == expected_model


async def test_same_entity_is_not_discovered_twice(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
        title="Test",
        source=SOURCE_INTEGRATION_DISCOVERY,
        setup=False,
    )

    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 0


async def test_wled_not_discovered_twice(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    await create_mock_config_entry(
        hass,
        {
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
        unique_id="pc_a848face92cd",
        title="Test",
        source=SOURCE_INTEGRATION_DISCOVERY,
        setup=False,
    )

    mock_device_with_entities(hass, "light.test", "WLED", "FOSS")

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 0


async def test_wled_skipped_when_light_device_type_excluded(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    mock_device_with_entities(hass, "light.test", "WLED", "FOSS")

    await run_powercalc_setup(
        hass,
        {},
        {CONF_DISCOVERY: {CONF_EXCLUDE_DEVICE_TYPES: [DeviceType.LIGHT]}},
    )

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 0


async def test_govee_segment_lights_skipped(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """
    Govee segment lights should be skipped
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2834
    """
    mock_device(hass, "govee-device", "Govee", "H6076")

    mock_entities_in_registry(
        hass,
        {
            "light.floor_lamp_livingroom": {
                "unique_id": "gv2mqtt-F23DD0C844866B65",
                "platform": "mqtt",
                "device_id": "govee-device",
            },
            "light.floor_lamp_livingroom_segment_001": {
                "unique_id": "gv2mqtt-F23DD0C844866B65-0",
                "platform": "mqtt",
                "device_id": "govee-device",
            },
            "light.floor_lamp_livingroom_segment_002": {
                "unique_id": "gv2mqtt-F23DD0C844866B65-1",
                "platform": "mqtt",
                "device_id": "govee-device",
            },
            "light.floor_lamp_livingroom_segment_003": {
                "unique_id": "gv2mqtt-F23DD0C844866B65-2",
                "platform": "mqtt",
                "device_id": "govee-device",
            },
        },
    )

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1


async def test_get_power_profile_empty_manufacturer(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    mock_device_with_entities(hass, "light.test", "", "some model")

    source_entity = create_source_entity("light.test", hass)
    profile = await get_power_profile_by_source_entity(hass, source_entity)

    assert not profile
    assert not caplog.records


async def test_no_power_sensors_are_created_for_ignored_config_entries(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    unique_id = "abc"
    mock_device_with_entities(
        hass,
        "light.test",
        "Signify",
        "LCT010",
        unique_id=unique_id,
    )

    config_entry_unique_id = f"pc_{unique_id}"
    await create_mock_config_entry(
        hass,
        {
            CONF_UNIQUE_ID: config_entry_unique_id,
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "Signify",
            CONF_MODEL: "LCT010",
        },
        unique_id=config_entry_unique_id,
        source=SOURCE_IGNORE,
        setup=False,
    )

    await run_powercalc_setup(hass)

    assert not hass.states.get("sensor.test_power")
    assert "Already setup with discovery, skipping" in caplog.text


@pytest.mark.parametrize(
    "entity_entry,device_entry,model_info",
    [
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
            ),
            None,
            None,
        ),
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            build_device_entry(config_entry_id="test", id="a", manufacturer="foo", model="bar"),
            ModelInfo("foo", "bar", None),
        ),
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            build_device_entry(config_entry_id="test", id="b", manufacturer="foo", model="bar"),
            None,
        ),
        (
            RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id=uuid.uuid4(),
                platform="switch",
                device_id="a",
            ),
            build_device_entry(config_entry_id="test", id="a", manufacturer="foo", model="bar", model_id="barry"),
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
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await run_powercalc_setup(hass)

    await async_advance_time(hass, timedelta(hours=2), block=False)
    await hass.async_block_till_done(True)

    await async_advance_time(hass, timedelta(hours=2), block=False)
    await hass.async_block_till_done(True)

    assert len([record for record in caplog.records if "Start auto discovery" in record.message]) == 3


async def test_update_profile_service(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await run_powercalc_setup(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_LIBRARY,
        blocking=True,
    )

    assert len([record for record in caplog.records if "Start auto discovery" in record.message]) == 2


async def test_discovery_by_device(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    mock_device(hass, "ABC123", "test", "discovery_type_device")

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert mock_calls[0][1] == (DOMAIN,)
    assert mock_calls[0][2]["context"] == {CONF_SOURCE: SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == DUMMY_ENTITY_ID
    assert mock_calls[0][2]["data"][CONF_MANUFACTURER] == "test"
    assert mock_calls[0][2]["data"][CONF_MODEL] == "discovery_type_device"
    assert mock_calls[0][2]["data"][CONF_UNIQUE_ID] == "pc_ABC123"
    assert len(mock_calls) == 1


async def test_discovery_by_config_entry(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    source_entry = MockConfigEntry(domain="test", title="Shared integration")
    source_entry.add_to_hass(hass)
    mock_devices(
        hass,
        {
            f"device-{index}": {
                "config_entry_id": source_entry.entry_id,
                "manufacturer": "test",
                "model": "discovery_type_config_entry",
            }
            for index in range(6)
        },
    )

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0][1] == (DOMAIN,)
    assert mock_calls[0][2]["context"] == {CONF_SOURCE: SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == DUMMY_ENTITY_ID
    assert mock_calls[0][2]["data"][CONF_MANUFACTURER] == "test"
    assert mock_calls[0][2]["data"][CONF_MODEL] == "discovery_type_config_entry"
    assert mock_calls[0][2]["data"][CONF_UNIQUE_ID] == f"pc_config_entry_{source_entry.entry_id}"


async def test_composite_devices_are_ignored_for_device_discovery(
    hass: HomeAssistant,
) -> None:
    mocked_devices = mock_devices(
        hass,
        {
            "regular-device": {"manufacturer": "test", "model": "regular"},
            "composite-device": {"manufacturer": "test", "model": "composite"},
        },
    )
    regular_device = mocked_devices["regular-device"]
    composite_device = mocked_devices["composite-device"]
    discovery_manager = DiscoveryManager(hass, {})

    with patch(
        "custom_components.powercalc.discovery.is_composite_device_id",
        side_effect=lambda _hass, device_id: device_id == composite_device.id,
    ):
        devices = discovery_manager.get_devices()

    assert devices == [regular_device]


async def test_powercalc_sensors_are_ignored_for_discovery(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """Powercalc sensors should not be considered for discovery"""
    mock_device(hass, "my-device", "test", "generic-iot")
    mock_entities_in_registry(
        hass,
        {
            "sensor.test_powercalc": {"platform": "powercalc", "device_id": "my-device"},
            "sensor.test_other": {"platform": "other-platform", "device_id": "my-device"},
        },
    )

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1


@pytest.mark.parametrize(
    "entity_entries,expected_entities",
    [
        (
            [
                RegistryEntryWithDefaults(
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
                RegistryEntryWithDefaults(
                    entity_id="scene.test",
                    unique_id="1111",
                    platform="hue",
                    device_id="hue-device",
                ),
                RegistryEntryWithDefaults(
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
                RegistryEntryWithDefaults(
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
                RegistryEntryWithDefaults(
                    entity_id="switch.test",
                    unique_id="1111",
                    platform="mqtt",
                    device_id="some-device",
                ),
                RegistryEntryWithDefaults(
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
async def test_get_entities(
    hass: HomeAssistant,
    entity_entries: list[RegistryEntry],
    expected_entities: list[str],
) -> None:
    mock_registry(hass, {entity_entry.entity_id: entity_entry for entity_entry in entity_entries})
    discovery_manager = DiscoveryManager(hass, {})
    entity_ids = [entity.entity_id for entity in discovery_manager.get_entities()]
    assert entity_ids == expected_entities


async def test_discovery_enable_runtime(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_DISCOVERY: {
                CONF_ENABLED: False,
            },
        },
    )

    await run_powercalc_setup(hass)

    assert len(mock_flow_init.mock_calls) == 0

    new_data = entry.data.copy()
    new_data[CONF_DISCOVERY] = {CONF_ENABLED: True}
    hass.config_entries.async_update_entry(entry, data=new_data)
    await hass.async_block_till_done()

    assert len(mock_flow_init.mock_calls) == 1


async def test_discovery_disable_runtime(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    entry = await create_mock_global_config_entry(
        hass,
        {CONF_DISCOVERY: {CONF_ENABLED: True}},
    )

    await run_powercalc_setup(hass)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1

    new_data = entry.data.copy()
    new_data[CONF_DISCOVERY] = {CONF_ENABLED: False}
    hass.config_entries.async_update_entry(entry, data=new_data)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 0

    caplog.clear()
    await async_advance_time(hass, timedelta(hours=2), block=False)
    await hass.async_block_till_done(True)

    assert "Start auto discovery" not in caplog.text


@pytest.mark.parametrize(
    "global_config",
    [
        ({CONF_ENABLE_AUTODISCOVERY_DEPRECATED: False}),
        ({CONF_DISCOVERY: {CONF_ENABLED: False}}),
    ],
)
async def test_discovery_disabled(
    hass: HomeAssistant,
    global_config: dict[str, Any],
) -> None:
    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await run_powercalc_setup(hass, {}, global_config)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 0


async def test_discovery_skips_run_when_disabled(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    discovery_manager = DiscoveryManager(hass, {}, enabled=False)
    await discovery_manager.start_discovery()

    assert "Discovery manager is disabled, skipping discovery run" in caplog.text


async def test_discovery_process_is_locked(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    discovery_manager = DiscoveryManager(hass, {})
    discovery_manager._status = DiscoveryStatus.IN_PROGRESS  # noqa: SLF001
    await discovery_manager.start_discovery()

    assert "Discovery already in progress, skipping new discovery run" in caplog.text


async def test_discovery_compatible_integrations(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    """Test that only entities with compatible integrations are discovered."""

    mock_entities_in_registry(
        hass,
        {
            "light.hue_light": {"platform": "hue", "device_id": "hue-device-id"},
            "light.other_light": {"platform": "other", "device_id": "other-device-id"},
        },
    )
    mock_devices(
        hass,
        {
            "hue-device-id": {"manufacturer": "test", "model": "compatible_integrations"},
            "other-device-id": {"manufacturer": "test", "model": "compatible_integrations"},
        },
    )

    await run_powercalc_setup(hass)

    # Check that only the hue light has been discovered
    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == "light.hue_light"
