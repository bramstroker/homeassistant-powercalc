import logging

from homeassistant import data_entry_flow
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import DeviceSelector, SelectSelector
import pytest
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity, create_source_entity
from custom_components.powercalc.config_flow import PowercalcConfigFlow, Step
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_STANDBY_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CONF_SUB_PROFILE,
    CONF_VARIABLES,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.flow_helper.flows.library import CONF_CONFIRM_AUTODISCOVERED_MODEL, LibraryConfigFlow
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.library import ModelInfo
from custom_components.powercalc.power_profile.power_profile import DiscoveryBy
from tests.common import (
    create_mock_config_entry,
    mock_device,
    mock_device_with_entities,
    mock_devices,
    mock_entities_in_registry,
    set_states,
)
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    confirm_auto_discovered_model,
    goto_virtual_power_strategy_step,
    initialize_discovery_flow,
    initialize_options_flow,
    process_config_flow,
    select_manufacturer_and_model,
    select_menu_item,
    set_virtual_power_configuration,
)


async def test_manually_setup_from_library(
    hass: HomeAssistant,
) -> None:
    mock_device_with_entities(
        hass,
        "light.test",
        "ikea",
        "LED1545G12",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.VIRTUAL_POWER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "light.test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY

    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_manual_setup_from_library_skips_to_manufacturer_step(
    hass: HomeAssistant,
) -> None:
    """Test that the flow skips to the manufacturer step if the model is not found in the library."""
    mock_device_with_entities(
        hass,
        "light.test",
        "ikea",
        "LEEEEE",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.VIRTUAL_POWER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "light.test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER


async def test_manufacturer_listing_is_filtered_by_entity_domain(
    hass: HomeAssistant,
) -> None:
    mock_entities_in_registry(hass, {"light.test": {"unique_id": DEFAULT_UNIQUE_ID}})
    await set_states(hass, [("light.test", STATE_ON)])

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "Sonos"} not in manufacturer_options
    assert {"value": "signify", "label": "Signify"} in manufacturer_options


async def test_manufacturer_listing_is_filtered_by_entity_domain2(
    hass: HomeAssistant,
) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.LUT,
        {
            CONF_ENTITY_ID: "switch.test",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "Sonos"} not in manufacturer_options
    assert {"value": "shelly", "label": "Shelly"} in manufacturer_options


async def test_model_listing_falls_back_to_model_id_when_name_missing(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "light.test"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MANUFACTURER: "test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL

    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "composite_lut", "label": "composite_lut"} in model_options


async def test_fixed_power_is_skipped_when_only_self_usage_true(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test"},
    )
    result = await select_manufacturer_and_model(hass, result, "test", "smart_switch_with_pm_new")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_library_options_flow_raises_error_on_non_existing_power_profile(
    hass: HomeAssistant,
) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "foo",
            CONF_MODEL: "bar",
        },
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "model_not_supported"


async def test_composite_library_profile_options_flow_builds_menu(
    hass: HomeAssistant,
) -> None:
    mock_device(hass, "vacuum1", "roborock", "rockrobo.vacuum.v1")

    mock_entities_in_registry(
        hass,
        {
            "vacuum.robi": {"device_id": "vacuum1", "platform": "test"},
            "sensor.robi_battery": {
                "device_id": "vacuum1",
                "device_class": SensorDeviceClass.BATTERY,
                "platform": "test",
            },
        },
    )

    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "vacuum.robi",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "roborock",
            CONF_MODEL: "rockrobo.vacuum.v1",
        },
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    assert result["menu_options"] == [
        Step.BASIC_OPTIONS,
        Step.LIBRARY_OPTIONS,
        Step.SELECT_DEVICE,
        Step.ADVANCED_OPTIONS,
    ]


async def test_change_manufacturer_model_from_options_flow(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "ikea",
            CONF_MODEL: "LED1545G12",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MANUFACTURER: "signify"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MODEL: "LWB010"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MANUFACTURER] == "signify"
    assert entry.data[CONF_MODEL] == "LWB010"


async def test_device_discovered_entry_keeps_device_type_filter_in_library_options(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "BSB002",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER

    manufacturer_select: SelectSelector = result["data_schema"].schema[CONF_MANUFACTURER]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "signify", "label": "Signify"} in manufacturer_options

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MANUFACTURER: "signify"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL

    model_select: SelectSelector = result["data_schema"].schema[CONF_MODEL]
    model_options = model_select.config["options"]
    option_values = [option["value"] for option in model_options]
    assert "BSB002" in option_values
    assert "LCT010" not in option_values


async def test_config_entry_discovered_entry_keeps_discovery_filter_in_library_options(hass: HomeAssistant) -> None:
    mock_devices(
        hass,
        {
            "selected-device": {
                "config_entry_id": "source-entry",
                "manufacturer": "test",
                "model": "discovery_type_config_entry",
            },
        },
    )
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_DEVICE: "selected-device",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_config_entry",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MANUFACTURER: "test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL
    model_select: SelectSelector = result["data_schema"].schema[CONF_MODEL]
    option_values = [option["value"] for option in model_select.config["options"]]
    assert "discovery_type_config_entry" in option_values
    assert "discovery_type_device" not in option_values


async def test_change_device_from_options_flow(hass: HomeAssistant) -> None:
    """The device selected during setup must be changeable from the options flow."""
    mock_devices(
        hass,
        {
            f"device-{index}": {
                "config_entry_id": "source-entry",
                "name": f"Device {index}",
                "manufacturer": "test",
                "model": "discovery_type_config_entry",
            }
            for index in range(3)
        },
    )
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_DEVICE: "device-0",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_config_entry",
            CONF_NAME: "Shared integration",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.SELECT_DEVICE)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    device_select: SelectSelector = result["data_schema"].schema[CONF_DEVICE]
    assert [option["value"] for option in device_select.config["options"]] == [
        "device-0",
        "device-1",
        "device-2",
    ]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE: "device-2"},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DEVICE] == "device-2"

    registry_entry = er.async_get(hass).async_get("sensor.shared_integration_power")
    assert registry_entry
    assert registry_entry.device_id == "device-2"


@pytest.mark.parametrize("configured_device", ["selected-device", "removed-device"])
async def test_select_device_omitted_from_options_menu_when_no_alternative_device(
    hass: HomeAssistant,
    configured_device: str,
) -> None:
    """Only offer the device selection when there is something to choose from."""
    mock_devices(
        hass,
        {
            "selected-device": {
                "config_entry_id": "source-entry",
                "manufacturer": "test",
                "model": "discovery_type_config_entry",
            },
        },
    )
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_DEVICE: configured_device,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_config_entry",
        },
    )

    result = await hass.config_entries.options.async_init(entry.entry_id, data=None)

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert Step.SELECT_DEVICE not in result["menu_options"]


async def test_change_device_from_options_flow_discovery_by_device(hass: HomeAssistant) -> None:
    """The source device of a device discovered profile must be changeable from the options flow."""
    mock_devices(
        hass,
        {
            "device-a": {"manufacturer": "test", "model": "discovery_type_device"},
            "device-b": {"manufacturer": "test", "model": "discovery_type_device"},
        },
    )
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_DEVICE: "device-a",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_device",
            CONF_NAME: "Some switch",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.SELECT_DEVICE)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert isinstance(result["data_schema"].schema[vol.Required(CONF_DEVICE)], DeviceSelector)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE: "device-b"},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DEVICE] == "device-b"

    registry_entry = er.async_get(hass).async_get("sensor.some_switch_device_power")
    assert registry_entry
    assert registry_entry.device_id == "device-b"


async def test_change_device_from_options_flow_discovery_by_entity(hass: HomeAssistant) -> None:
    """Entity discovered profiles can be linked to another device, and unlinked again."""
    mock_devices(
        hass,
        {
            "source-device": {"manufacturer": "signify", "model": "LCT010"},
            "other-device": {"manufacturer": "signify", "model": "LCT010"},
        },
    )
    mock_entities_in_registry(hass, {"light.test": {"device_id": "source-device", "platform": "hue"}})
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
            CONF_NAME: "Test",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.SELECT_DEVICE)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert isinstance(result["data_schema"].schema[vol.Optional(CONF_DEVICE)], DeviceSelector)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE: "other-device"},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DEVICE] == "other-device"

    # Submitting the form without a device unlinks it again, so the source entity device is used.
    result = await initialize_options_flow(hass, entry, Step.SELECT_DEVICE)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={})
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert CONF_DEVICE not in entry.data


async def test_change_sub_profile_options_flow(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "yeelight",
            CONF_MODEL: "YLDD04YL/standard_length",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MANUFACTURER: "yeelight"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MODEL: "YLDD04YL"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.SUB_PROFILE

    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SUB_PROFILE: "extension_5x1meter"},
    )

    assert entry.data[CONF_MANUFACTURER] == "yeelight"
    assert entry.data[CONF_MODEL] == "YLDD04YL/extension_5x1meter"


async def test_configured_model_populated_in_options_flow(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_MANUFACTURER)].description == {
        "suggested_value": "signify",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MANUFACTURER: "signify"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_MODEL)].description == {
        "suggested_value": "LCT010",
    }
    model_select: SelectSelector = result["data_schema"].schema[CONF_MODEL]
    model_options = model_select.config["options"]
    assert {"value": "LCT010", "label": "LCT010 (Hue White and Color Ambiance A19 E26 (Gen 3))"} in model_options
    assert {"value": "LCA001", "label": "LCA001 (Hue White and Color Ambiance A19 E26/E27 (Gen 5))"} in model_options

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MODEL: "LCA001"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MANUFACTURER] == "signify"
    assert entry.data[CONF_MODEL] == "LCA001"


async def test_source_entity_not_visible_in_options_when_discovery_by_device(hass: HomeAssistant) -> None:
    """When discovery mode was by device, source entity should not be visible in options."""
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "discovery_type_device",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert CONF_ENTITY_ID not in result["data_schema"].schema


@pytest.mark.parametrize(
    "source_entity, expected_discovery_by",
    [
        (None, None),
        (
            SourceEntity(
                object_id="source-entry",
                entity_id=DUMMY_ENTITY_ID,
                domain="sensor",
                config_entry_id="source-entry",
            ),
            DiscoveryBy.CONFIG_ENTRY,
        ),
    ],
    ids=["no_source", "config_entry"],
)
def test_library_discovery_filter(
    source_entity: SourceEntity | None,
    expected_discovery_by: DiscoveryBy | None,
) -> None:
    """The library listing is filtered using the active discovery context."""
    flow = PowercalcConfigFlow()
    flow.source_entity = source_entity

    assert LibraryConfigFlow(flow)._get_library_discovery_by() == expected_discovery_by  # noqa: SLF001


async def test_profile_with_custom_fields(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    mock_device_with_entities(
        hass,
        ["sensor.test", "sensor.foobar"],
        "test",
        "custom_fields",
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await process_config_flow(
        hass,
        result,
        {
            Step.VIRTUAL_POWER: {
                CONF_ENTITY_ID: "sensor.test",
            },
            Step.LIBRARY: {
                CONF_CONFIRM_AUTODISCOVERED_MODEL: True,
            },
            Step.LIBRARY_CUSTOM_FIELDS: {
                "some_entity": "sensor.foobar",
            },
            Step.POWER_ADVANCED: {},
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_STANDBY_ENERGY_SENSOR: False,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
        CONF_ENERGY_FILTER_OUTLIER_ENABLED: False,
        CONF_ENTITY_ID: "sensor.test",
        CONF_NAME: "test",
        CONF_MANUFACTURER: "test",
        CONF_MODEL: "custom_fields",
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_VARIABLES: {
            "some_entity": "sensor.foobar",
        },
    }

    assert not caplog.records


async def test_manual_library_flow_autodiscovers_device_profile_with_custom_fields(
    hass: HomeAssistant,
) -> None:
    mock_device(hass, "test-device", "test", "device_custom_fields")
    mock_entities_in_registry(
        hass,
        {
            "switch.test_device": {"unique_id": "test-switch", "platform": "test", "device_id": "test-device"},
            "sensor.test_dependency": {"unique_id": "test-dependency", "platform": "test", "device_id": "test-device"},
        },
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test_device"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY


async def test_manual_library_flow_defers_device_profile_custom_field_validation(
    hass: HomeAssistant,
) -> None:
    mock_device(hass, "test-device", "test", "device_custom_fields")
    mock_entities_in_registry(
        hass,
        {
            "switch.test_device": {"unique_id": "test-switch", "platform": "test", "device_id": "test-device"},
            "sensor.test_dependency": {"unique_id": "test-dependency", "platform": "test", "device_id": "test-device"},
        },
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test_device"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY_CUSTOM_FIELDS


async def test_sub_profiles_select_options(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test"},
    )
    result = await select_manufacturer_and_model(hass, result, "test", "sub_profile")
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.SUB_PROFILE
    assert result["description_placeholders"]["remarks"] == "\n\nMore info\n\nBla bla\n*Bla bla*"

    data_schema: vol.Schema = result["data_schema"]
    sub_profile_selector: SelectSelector = data_schema.schema["sub_profile"]
    options = sub_profile_selector.config["options"]
    assert options == [{"label": "Name A", "value": "a"}, {"label": "Name B", "value": "b"}]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SUB_PROFILE: "a"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_sub_profile_selection_available_default_sub_profile(hass: HomeAssistant) -> None:
    """
    Test the sub profile selection is still provided to the user, even when a default sub profile is defined.
    We only want to omit the sub profile step when matchers are defined.
    """
    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test"},
    )
    result = await select_manufacturer_and_model(hass, result, "test", "sub_profile_default")

    data_schema: vol.Schema = result["data_schema"]
    sub_profile_selector: SelectSelector = data_schema.schema["sub_profile"]
    options = sub_profile_selector.config["options"]
    assert options == [{"label": "Name A", "value": "a"}, {"label": "Name B", "value": "b"}]


async def test_sub_profile_selection_omitted(hass: HomeAssistant) -> None:
    """
    Test the sub profile selection is omitted when matchers are defined.
    """
    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "switch.test"},
    )
    result = await select_manufacturer_and_model(hass, result, "test", "sub_profile_matchers")
    assert result["step_id"] != Step.SUB_PROFILE


async def test_sub_profile_selection_discovery_by_device(
    hass: HomeAssistant,
) -> None:
    """
    Test that sub profile selection is available when discovery_by is device
    Also make sure the step is sub_profile_per_device so the description translation is correct
    see: https://github.com/bramstroker/homeassistant-powercalc/issues/3866
    """

    mock_device_with_entities(hass, "switch.test", "test", "discovery_type_device_sub_profile")

    source_entity = create_source_entity("switch.test", hass)
    result = await initialize_discovery_flow(hass, source_entity)

    result = await confirm_auto_discovered_model(hass, result)

    assert result["step_id"] == Step.AVAILABILITY_ENTITY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AVAILABILITY_ENTITY: "switch.test"},
    )

    assert result["step_id"] == Step.SUB_PROFILE_PER_DEVICE

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SUB_PROFILE: "a"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_discovery_flow_documentation_url_in_remarks(hass: HomeAssistant) -> None:
    """When model.json has documentation_url, it should appear as a link in the discovery remarks."""
    source_entity = create_source_entity("sensor.test", hass)
    power_profile = await get_power_profile(hass, {}, source_entity, ModelInfo("test", "ups"), process_variables=False)
    result = await initialize_discovery_flow(hass, source_entity, power_profile)

    assert result["step_id"] == Step.LIBRARY
    remarks = result["description_placeholders"]["remarks"]
    assert "[Documentation](https://docs.powercalc.nl/cookbook/ups/)" in remarks


async def test_custom_fields_documentation_url_placeholder(
    hass: HomeAssistant,
) -> None:
    """When model.json has documentation_url, the custom fields step should include it in description_placeholders."""
    mock_device_with_entities(
        hass,
        ["sensor.test", "sensor.load"],
        "test",
        "ups",
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "sensor.test"},
    )
    assert result["step_id"] == Step.LIBRARY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )
    assert result["step_id"] == Step.LIBRARY_CUSTOM_FIELDS
    assert result["description_placeholders"]["documentation_url"] == "https://docs.powercalc.nl/cookbook/ups/"


async def test_options_flow_initializes_profile_with_custom_fields(
    hass: HomeAssistant,
) -> None:
    mock_device(hass, "test-device", "test", "device_custom_fields")
    mock_entities_in_registry(
        hass,
        {
            "switch.test_device": {"unique_id": "test-switch", "platform": "test", "device_id": "test-device"},
            "sensor.test_dependency": {"unique_id": "test-dependency", "platform": "test", "device_id": "test-device"},
        },
    )

    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.test_device",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "device_custom_fields",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_VARIABLES: {
                "some_entity": "sensor.test_dependency",
            },
        },
    )

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY_OPTIONS


async def test_availability_entity_step_skipped(hass: HomeAssistant) -> None:
    mock_devices(
        hass,
        {
            "test-device": {"manufacturer": "test", "name": "Test Device", "model": "discovery_type_device"},
        },
    )

    source_entity = create_source_entity(DUMMY_ENTITY_ID, hass)
    power_profiles = [
        await get_power_profile(hass, {}, source_entity, ModelInfo("test", "discovery_type_device")),
    ]
    result = await initialize_discovery_flow(hass, source_entity, power_profiles)
    result = await confirm_auto_discovered_model(hass, result)
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
