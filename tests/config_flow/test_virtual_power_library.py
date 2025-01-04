import logging

import pytest
import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import SelectSelector

from custom_components.powercalc import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
)
from custom_components.powercalc.config_flow import (
    CONF_CONFIRM_AUTODISCOVERED_MODEL,
    Step,
)
from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CONF_VARIABLES,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight
from tests.common import create_mock_light_entity, get_test_config_dir
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    select_menu_item,
    set_virtual_power_configuration,
)
from tests.conftest import MockEntityWithModel


async def test_manually_setup_from_library(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
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
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Test that the flow skips to the manufacturer step if the model is not found in the library."""
    mock_entity_with_model_information(
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
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "sonos"} not in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options


async def test_manufacturer_listing_is_filtered_by_entity_domain2(
    hass: HomeAssistant,
) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.LUT,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.LUT,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "sonos"} not in manufacturer_options
    assert {"value": "shelly", "label": "shelly"} in manufacturer_options


async def test_library_options_flow_raises_error_on_non_existing_power_profile(
    hass: HomeAssistant,
) -> None:
    entry = create_mock_entry(
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


async def test_change_manufacturer_model_from_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
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


async def test_source_entity_not_visible_in_options_when_discovery_by_device(hass: HomeAssistant) -> None:
    """When discovery mode was by device, source entity should not be visible in options."""
    hass.config.config_dir = get_test_config_dir()
    entry = create_mock_entry(
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


async def test_profile_with_custom_fields(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    hass.config.config_dir = get_test_config_dir()
    mock_entity_with_model_information(
        "sensor.test",
        "test",
        "custom_fields",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.VIRTUAL_POWER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "sensor.test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY_CUSTOM_FIELDS

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"some_entity": "sensor.foobar"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.POWER_ADVANCED
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
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
