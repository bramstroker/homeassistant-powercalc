import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.selector import SelectSelector
from pytest_homeassistant_custom_component.common import mock_device_registry, mock_registry

from custom_components.powercalc.common import SourceEntity, create_source_entity
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CONF_SUB_PROFILE,
    DUMMY_ENTITY_ID,
    SensorType,
)
from custom_components.powercalc.discovery import get_power_profile_by_source_entity
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.library import ModelInfo
from tests.common import get_test_config_dir
from tests.config_flow.common import (
    DEFAULT_ENTITY_ID,
    DEFAULT_UNIQUE_ID,
    confirm_auto_discovered_model,
    create_mock_entry,
    initialize_discovery_flow,
    initialize_options_flow,
)
from tests.conftest import MockEntityWithModel


async def test_discovery_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        "light.test",
        "signify",
        "LCT010",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    source_entity = await create_source_entity(DEFAULT_ENTITY_ID, hass)
    result = await initialize_discovery_flow(hass, source_entity)

    # Confirm selected manufacturer/model
    result = await confirm_auto_discovered_model(hass, result)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "signify",
        CONF_MODEL: "LCT010",
        CONF_NAME: "test",
    }


async def test_discovery_flow_remarks_are_shown(hass: HomeAssistant) -> None:
    """Model.json can provide remarks to show in the discovery flow. Check if these are displayed correctly"""
    source_entity = await create_source_entity("media_player.test", hass)
    power_profile = await get_power_profile(hass, {}, ModelInfo("sonos", "one"))
    result = await initialize_discovery_flow(hass, source_entity, power_profile)
    assert result["description_placeholders"]["remarks"] is not None


async def test_discovery_flow_with_subprofile_selection(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        "light.test",
        "lifx",
        "LIFX Z",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    source_entity = await create_source_entity(DEFAULT_ENTITY_ID, hass)
    power_profile = await get_power_profile_by_source_entity(hass, source_entity)

    result = await initialize_discovery_flow(hass, source_entity, power_profile)

    result = await confirm_auto_discovered_model(hass, result)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.SUB_PROFILE
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SUB_PROFILE: "length_6"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "lifx",
        CONF_MODEL: "LIFX Z/length_6",
        CONF_NAME: "test",
    }


async def test_discovery_flow_multi_profiles(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Test that discovery provides the user with a choice when multiple profiles are available"""
    mock_entity_with_model_information(
        "light.test",
        "signify",
        "LCT010",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    source_entity = await create_source_entity(DEFAULT_ENTITY_ID, hass)
    power_profiles = [
        await get_power_profile(hass, {}, ModelInfo("signify", "LCT010")),
        await get_power_profile(hass, {}, ModelInfo("signify", "LCT012")),
    ]
    result = await initialize_discovery_flow(hass, source_entity, power_profiles)

    assert result["step_id"] == Step.LIBRARY_MULTI_PROFILE
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    data_schema: vol.Schema = result["data_schema"]
    select: SelectSelector = data_schema.schema[CONF_MODEL]
    options = select.config["options"]
    assert len(options) == 2
    option_labels = [option["label"] for option in options]
    assert option_labels == ["LCT010", "LCT012"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MODEL: options[1]["value"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "signify",
        CONF_MODEL: "LCT012",
        CONF_NAME: "test",
    }


async def test_autodiscovered_option_flow(hass: HomeAssistant) -> None:
    """
    Test that we can open an option flow for an auto discovered config entry
    """
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_NAME: "Test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
        config_entries.SOURCE_INTEGRATION_DISCOVERY,
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {CONF_CREATE_ENERGY_SENSOR: False}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_CREATE_ENERGY_SENSOR]


async def test_discovery_by_device(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()

    device_entry = DeviceEntry(
        name="FooBar",
        id="youless-device",
        manufacturer="test",
        model="discovery_type_device",
    )
    mock_device_registry(
        hass,
        {
            device_entry.id: device_entry,
        },
    )
    mock_registry(
        hass,
        {
            "switch.test": RegistryEntry(
                entity_id="switch.test",
                unique_id="54543",
                device_id=device_entry.id,
                platform="youless",
            ),
        },
    )
    source_entity = SourceEntity(
        object_id=device_entry.name,
        name=device_entry.name,
        entity_id=DUMMY_ENTITY_ID,
        domain="sensor",
        device_entry=device_entry,
    )
    power_profiles = [
        await get_power_profile(hass, {}, ModelInfo("test", "discovery_type_device")),
    ]
    result = await initialize_discovery_flow(hass, source_entity, power_profiles)

    result = await confirm_auto_discovered_model(hass, result)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.AVAILABILITY_ENTITY
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AVAILABILITY_ENTITY: "switch.test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_AVAILABILITY_ENTITY: "switch.test",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "test",
        CONF_MODEL: "discovery_type_device",
        CONF_NAME: "FooBar",
        CONF_DEVICE: "youless-device",
    }

    assert hass.states.get("sensor.foobar_device_power")
