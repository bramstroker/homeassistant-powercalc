import asyncio
from datetime import timedelta
from typing import Any

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES, CONF_GROUP_UPDATE_INTERVAL, DEFAULT_GROUP_UPDATE_INTERVAL, DeviceType
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_UTILITY_METER_TYPES,
    DOMAIN,
    DOMAIN_CONFIG,
    ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
    SensorType,
    UnitPrefix,
)
from tests.common import get_simple_fixed_config, run_powercalc_setup
from tests.config_flow.common import (
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)


async def test_config_flow(hass: HomeAssistant) -> None:
    """Test full configuration flow."""
    await run_powercalc_setup(hass, {}, {})

    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DISABLE_LIBRARY_DOWNLOAD: True,
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_POWER_SENSOR_PRECISION: 4,
            CONF_FORCE_UPDATE_FREQUENCY: 300,
            CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES: [DeviceType.SMART_SWITCH],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_ENERGY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_UTILITY_METER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["foo"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CREATE_DOMAIN_GROUPS: [],
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_UTILITY_METERS: True,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_DISABLE_LIBRARY_DOWNLOAD: True,
        CONF_ENABLE_AUTODISCOVERY: True,
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        CONF_ENERGY_SENSOR_CATEGORY: None,
        CONF_ENERGY_SENSOR_NAMING: "{} energy",
        CONF_ENERGY_SENSOR_PRECISION: 4,
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
        CONF_FORCE_UPDATE_FREQUENCY: 300,
        CONF_GROUP_UPDATE_INTERVAL: DEFAULT_GROUP_UPDATE_INTERVAL,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_POWER_SENSOR_CATEGORY: None,
        CONF_POWER_SENSOR_NAMING: "{} power",
        CONF_POWER_SENSOR_PRECISION: 4,
        CONF_UTILITY_METER_NET_CONSUMPTION: False,
        CONF_UTILITY_METER_OFFSET: 0,
        CONF_UTILITY_METER_TARIFFS: ["foo"],
        CONF_UTILITY_METER_TYPES: [DAILY],
        CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES: [DeviceType.SMART_SWITCH],
    }
    config_entry: ConfigEntry = result["result"]
    assert config_entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
    assert global_config[CONF_DISABLE_LIBRARY_DOWNLOAD]
    assert global_config[CONF_POWER_SENSOR_PRECISION] == 4
    assert global_config[CONF_FORCE_UPDATE_FREQUENCY] == timedelta(seconds=300)


@pytest.mark.parametrize(
    "user_input,expected_step",
    [
        ({CONF_CREATE_ENERGY_SENSORS: False, CONF_CREATE_UTILITY_METERS: True}, Step.GLOBAL_CONFIGURATION_UTILITY_METER),
        ({CONF_CREATE_ENERGY_SENSORS: True, CONF_CREATE_UTILITY_METERS: True}, Step.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSORS: True, CONF_CREATE_UTILITY_METERS: False}, Step.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSORS: False, CONF_CREATE_UTILITY_METERS: False}, None),
    ],
)
async def test_energy_and_utility_options_skipped(hass: HomeAssistant, user_input: dict[str, Any], expected_step: Step | None) -> None:
    """Test the energy and utility_meter options are only shown when relevant."""
    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    if expected_step:
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == expected_step
    else:
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_initialize_options_succeeds_with_yaml_sensors_in_config(hass: HomeAssistant) -> None:
    """Test options flow is initialized when sensors are defined in YAML configuration."""
    entry = create_mock_global_config_entry(
        hass,
        {},
    )

    await run_powercalc_setup(hass, get_simple_fixed_config("input_boolean.test", 50), {})

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION)
    assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_global_configuration_can_only_be_configured_once(hass: HomeAssistant) -> None:
    """Test global configuration can only be configured once."""
    create_mock_global_config_entry(
        hass,
        {},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert Step.GLOBAL_CONFIGURATION not in result["menu_options"]


async def test_basic_options_flow(hass: HomeAssistant) -> None:
    """Test basic options flow."""
    entry = create_mock_global_config_entry(
        hass,
        {},
    )

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION)

    user_input = {
        CONF_POWER_SENSOR_PRECISION: 4,
        CONF_POWER_SENSOR_NAMING: "{} power_watt",
        CONF_POWER_SENSOR_FRIENDLY_NAMING: "{} friendly",
        CONF_POWER_SENSOR_CATEGORY: EntityCategory.CONFIG,
        CONF_FORCE_UPDATE_FREQUENCY: 20,
        CONF_IGNORE_UNAVAILABLE_STATE: True,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: False,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: True,
        CONF_DISABLE_LIBRARY_DOWNLOAD: False,
        CONF_CREATE_ENERGY_SENSORS: False,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    # Check if config entry data is updated.
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_POWER_SENSOR_PRECISION] == 4
    assert entry.data[CONF_POWER_SENSOR_NAMING] == "{} power_watt"
    assert entry.data[CONF_POWER_SENSOR_FRIENDLY_NAMING] == "{} friendly"
    assert entry.data[CONF_POWER_SENSOR_CATEGORY] == EntityCategory.CONFIG
    assert entry.data[CONF_FORCE_UPDATE_FREQUENCY] == 20
    assert entry.data[CONF_IGNORE_UNAVAILABLE_STATE]
    assert not entry.data[CONF_INCLUDE_NON_POWERCALC_SENSORS]
    assert entry.data[CONF_DISABLE_EXTENDED_ATTRIBUTES]
    assert not entry.data[CONF_DISABLE_LIBRARY_DOWNLOAD]
    assert not entry.data[CONF_CREATE_ENERGY_SENSORS]

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_POWER_SENSOR_PRECISION] == 4


async def test_energy_options_flow(hass: HomeAssistant) -> None:
    """Test energy options flow."""
    entry = create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION_ENERGY)

    user_input = {
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        CONF_ENERGY_SENSOR_PRECISION: 5,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    # Check if config entry data is updated.
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_TRAPEZODIAL
    assert entry.data[CONF_ENERGY_SENSOR_PRECISION] == 5

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_TRAPEZODIAL
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_SENSOR_PRECISION] == 5


async def test_utility_meter_options_flow(hass: HomeAssistant) -> None:
    """Test utility meter options flow."""
    entry = create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION_UTILITY_METER)

    user_input = {
        CONF_UTILITY_METER_TYPES: [DAILY],
        CONF_UTILITY_METER_TARIFFS: ["peak", "off_peak"],
        CONF_UTILITY_METER_OFFSET: 1,
        CONF_UTILITY_METER_NET_CONSUMPTION: True,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    # Check if config entry data is updated.
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_UTILITY_METER_TYPES] == [DAILY]
    assert entry.data[CONF_UTILITY_METER_TARIFFS] == ["peak", "off_peak"]
    assert entry.data[CONF_UTILITY_METER_OFFSET] == 1
    assert entry.data[CONF_UTILITY_METER_NET_CONSUMPTION]

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_TYPES] == [DAILY]
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_TARIFFS] == ["peak", "off_peak"]
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_OFFSET] == timedelta(days=1)
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_NET_CONSUMPTION]


async def test_entities_are_reloaded_reflecting_changes(hass: HomeAssistant) -> None:
    """Test entities are reloaded reflecting changes."""

    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "abcdef",
            CONF_ENTITY_ID: "light.test",
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id="abcdef",
        title="Mock sensor",
    )
    config_entry.add_to_hass(hass)

    global_config_entry = create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FORCE_UPDATE_FREQUENCY: 1200,
        },
    )
    await hass.config_entries.async_setup(global_config_entry.entry_id)

    await run_powercalc_setup(hass, {}, {})

    assert hass.states.get("sensor.test_power").state == "50.00"

    result = await initialize_options_flow(hass, global_config_entry, Step.GLOBAL_CONFIGURATION)

    user_input = {
        CONF_POWER_SENSOR_PRECISION: 4,
    }
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    await asyncio.sleep(0.1)

    assert hass.states.get("sensor.test_power").state == "50.0000"


def create_mock_global_config_entry(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    """Create a mock entry."""
    return create_mock_entry(
        hass,
        {
            CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
            CONF_POWER_SENSOR_PRECISION: DEFAULT_POWER_SENSOR_PRECISION,
            CONF_POWER_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
            CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
            CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
            CONF_ENERGY_SENSOR_PRECISION: DEFAULT_ENERGY_SENSOR_PRECISION,
            CONF_ENERGY_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
            CONF_FORCE_UPDATE_FREQUENCY: 600,
            CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_CREATE_DOMAIN_GROUPS: [],
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_ENABLE_AUTODISCOVERY: True,
            CONF_UTILITY_METER_OFFSET: 0,
            CONF_UTILITY_METER_TYPES: DEFAULT_UTILITY_METER_TYPES,
            CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
            **data,
        },
        unique_id=ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    )
