from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.config_flow import CONF_CONFIRM_AUTODISCOVERED_MODEL, Steps
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CONF_SUB_PROFILE,
    SensorType,
)
from custom_components.powercalc.discovery import get_power_profile_by_source_entity
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.library import ModelInfo
from tests.config_flow.common import (
    DEFAULT_ENTITY_ID,
    DEFAULT_UNIQUE_ID,
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
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "signify",
        CONF_MODEL: "LCT010",
        CONF_NAME: "test",
        CONF_UNIQUE_ID: f"pc_{DEFAULT_UNIQUE_ID}",
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

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.SUB_PROFILE
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
        CONF_UNIQUE_ID: f"pc_{DEFAULT_UNIQUE_ID}",
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

    result = await initialize_options_flow(hass, entry, Steps.BASIC_OPTIONS)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {CONF_CREATE_ENERGY_SENSOR: False}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_CREATE_ENERGY_SENSOR]
