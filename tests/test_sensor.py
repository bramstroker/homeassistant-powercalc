import logging
from datetime import timedelta
from unittest.mock import patch

import homeassistant.helpers.entity_registry as er
import pytest
from homeassistant.components import light, sensor
from homeassistant.components.integration.sensor import ATTR_SOURCE_ID
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.utility_meter.sensor import ATTR_PERIOD, DAILY, HOURLY
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
    STATE_OFF,
    STATE_ON,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import (
    DeviceEntry,
    DeviceEntryDisabler,
    DeviceRegistry,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENTITIES,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)

from .common import (
    create_input_boolean,
    create_input_booleans,
    get_simple_fixed_config,
    run_powercalc_setup,
)
from .conftest import MockEntityWithModel


async def test_fixed_power_sensor_from_yaml(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "0.00"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "50.00"
    assert (
        power_state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.FIXED
    )
    assert power_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER

    energy_state = hass.states.get("sensor.test_energy")
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert (
        energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfEnergy.KILO_WATT_HOUR
    )
    assert energy_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_power"
    assert energy_state.attributes.get(ATTR_SOURCE_ENTITY) == "input_boolean.test"


async def test_legacy_yaml_platform_configuration(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    assert await async_setup_component(
        hass,
        sensor.DOMAIN,
        {
            sensor.DOMAIN: {
                CONF_PLATFORM: DOMAIN,
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_FIXED: {CONF_POWER: 50},
            },
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power")
    assert issue_registry.async_get_issue(DOMAIN, "powercalc_deprecated_yaml")


async def test_utility_meter_is_created(hass: HomeAssistant) -> None:
    """Test that utility meters are succesfully created when `create_utility_meter: true`"""
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY, HOURLY],
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    daily_state = hass.states.get("sensor.test_energy_daily")
    assert daily_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_energy"
    assert daily_state.attributes.get(ATTR_PERIOD) == DAILY

    hourly_state = hass.states.get("sensor.test_energy_hourly")
    assert hourly_state
    assert hourly_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_energy"
    assert hourly_state.attributes.get(ATTR_PERIOD) == HOURLY

    monthly_state = hass.states.get("sensor.test_energy_monthly")
    assert not monthly_state


async def test_create_nested_group_sensor(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test", "test1", "test2"])

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup1",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test", 50),
                get_simple_fixed_config("input_boolean.test1", 50),
                {
                    CONF_CREATE_GROUP: "TestGroup2",
                    CONF_ENTITIES: [
                        get_simple_fixed_config("input_boolean.test2", 50),
                    ],
                },
            ],
        },
    )

    hass.states.async_set("input_boolean.test", STATE_ON)
    hass.states.async_set("input_boolean.test1", STATE_ON)
    hass.states.async_set("input_boolean.test2", STATE_ON)

    await hass.async_block_till_done()

    group1 = hass.states.get("sensor.testgroup1_power")
    assert group1.attributes[ATTR_ENTITIES] == {
        "sensor.test_power",
        "sensor.test1_power",
        "sensor.test2_power",
    }
    assert group1.state == "150.00"

    group2 = hass.states.get("sensor.testgroup2_power")
    assert group2.attributes[ATTR_ENTITIES] == {
        "sensor.test2_power",
    }
    assert group2.state == "50.00"

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        hass.states.async_set("input_boolean.test2", STATE_OFF)
        await hass.async_block_till_done()

    group1 = hass.states.get("sensor.testgroup1_power")
    assert group1.state == "100.00"

    group2 = hass.states.get("sensor.testgroup2_power")
    assert group2.state == "0.00"


async def test_light_lut_strategy(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    light_entity_id = "light.test1"
    mock_entity_with_model_information(
        light_entity_id,
        "signify",
        "LWB010",
        capabilities={ATTR_SUPPORTED_COLOR_MODES: [light.ColorMode.BRIGHTNESS]},
    )
    hass.states.async_set(
        light_entity_id,
        STATE_ON,
        {ATTR_BRIGHTNESS: 125, ATTR_COLOR_MODE: light.ColorMode.BRIGHTNESS},
    )

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: light_entity_id},
    )

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "2.67"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.LUT
    assert state.attributes.get(ATTR_SOURCE_ENTITY) == light_entity_id


async def test_error_when_configuring_same_entity_twice(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("input_boolean.test", 50),
            get_simple_fixed_config("input_boolean.test", 100),
        ],
    )

    assert "This entity has already configured a power sensor" in caplog.text
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_alternate_naming_strategy(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {CONF_POWER: 25},
        },
        {
            CONF_POWER_SENSOR_NAMING: "{} Power consumption",
            CONF_POWER_SENSOR_FRIENDLY_NAMING: "{} Power friendly",
            CONF_ENERGY_SENSOR_NAMING: "{} Energy kwh",
            CONF_ENERGY_SENSOR_FRIENDLY_NAMING: "{} Energy friendly",
        },
    )
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power_consumption")
    assert power_state
    assert power_state.attributes.get(ATTR_FRIENDLY_NAME) == "test Power friendly"
    energy_state = hass.states.get("sensor.test_energy_kwh")
    assert energy_state
    assert energy_state.attributes.get(ATTR_FRIENDLY_NAME) == "test Energy friendly"


async def test_can_create_same_entity_twice_with_unique_id(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_UNIQUE_ID: "111",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 50},
            },
            {
                CONF_ENTITY_ID: "input_boolean.test",
                CONF_UNIQUE_ID: "222",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 100},
            },
        ],
    )

    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")
    assert hass.states.get("sensor.test_power_2")
    assert hass.states.get("sensor.test_energy_2")


async def test_unsupported_model_is_skipped_from_autodiscovery(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test", "lidl", "non_existing_model")

    # Run powercalc setup with autodiscovery
    await run_powercalc_setup(hass, {}, {})

    assert "Model not found in library, skipping discovery" in caplog.text


async def test_can_include_autodiscovered_entity_in_group(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """Test that models are automatically discovered and power sensors created"""

    caplog.set_level(logging.ERROR)

    mock_entity_with_model_information("light.testa", "lidl", "HG06462A")

    hass.states.async_set(
        "light.testa",
        STATE_ON,
        {"brightness": 125, "color_mode": ColorMode.BRIGHTNESS},
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "GroupA",
                CONF_ENTITIES: [{CONF_ENTITY_ID: "light.testa"}],
            },
        ],
        {CONF_ENABLE_AUTODISCOVERY: True},
    )

    assert len(caplog.records) == 0

    assert hass.states.get("sensor.testa_power")
    group_state = hass.states.get("sensor.groupa_power")
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.testa_power"}


async def test_user_can_rename_entity_id(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
) -> None:
    """
    When the power/energy sensors exist already with an unique ID, don't change the entity ID
    This allows the users to change the entity ID's from the GUI
    """
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="my_renamed_power",
    )
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef_energy",
        suggested_object_id="my_renamed_energy",
    )
    await hass.async_block_till_done()

    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_UNIQUE_ID: "abcdef",
            CONF_FIXED: {CONF_POWER: 40},
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.my_renamed_power")
    assert not hass.states.get("sensor.test_power")

    energy_state = hass.states.get("sensor.my_renamed_energy")
    assert energy_state
    assert energy_state.attributes.get("source") == "sensor.my_renamed_power"
    assert not hass.states.get("sensor.test_energy")


async def test_entities_are_bound_to_source_device(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
    device_reg: DeviceRegistry,
) -> None:
    """
    Test that all powercalc created sensors are attached to same device as the source entity
    """

    # Create a device
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", "abcdef")},
        manufacturer="Google Inc.",
        model="Google Home Mini",
    )

    # Create a source entity which is bound to the device
    unique_id = "34445329342797234"
    entity_reg.async_get_or_create(
        "switch",
        "switch",
        unique_id,
        suggested_object_id="google_home",
        device_id=device_entry.id,
    )
    await hass.async_block_till_done()

    # Create powercalc sensors
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "switch.google_home",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Assert that all the entities are bound to correct device
    power_entity_entry = entity_reg.async_get("sensor.google_home_power")
    assert power_entity_entry
    assert power_entity_entry.device_id == device_entry.id

    energy_entity_entry = entity_reg.async_get("sensor.google_home_energy")
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_entry.id

    utility_entity_entry = entity_reg.async_get("sensor.google_home_energy_daily")
    assert utility_entity_entry
    assert utility_entity_entry.device_id == device_entry.id


async def test_entities_are_bound_to_source_device2(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    When using the power_sensor_id option the energy sensors and utility meters must be bound to the same device.
    Also make sure no errors are logged
    """

    caplog.set_level(logging.ERROR)

    device_id = "device.test"
    switch_id = "switch.shelly"
    power_sensor_id = "sensor.shelly_power"

    mock_device_registry(
        hass,
        {device_id: DeviceEntry(id=device_id, manufacturer="shelly", model="Plug S")},
    )

    entity_reg = mock_registry(
        hass,
        {
            switch_id: er.RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id=device_id,
            ),
            power_sensor_id: er.RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="12345",
                platform="sensor",
                device_id=device_id,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "switch.shelly", CONF_POWER_SENSOR_ID: "sensor.shelly_power"},
        {},
    )

    energy_entity_entry = entity_reg.async_get("sensor.shelly_energy")
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id

    assert len(caplog.records) == 0


async def test_entities_are_bound_to_disabled_source_device(
    hass: HomeAssistant,
) -> None:
    device_id = "device.test"
    power_sensor_id = "sensor.test_power"
    light_id = "light.test"

    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="signify",
                model="LCA001",
                disabled_by=DeviceEntryDisabler.USER,
            ),
        },
    )

    entity_reg = mock_registry(
        hass,
        {
            light_id: er.RegistryEntry(
                entity_id=light_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="light",
                device_id=device_id,
            ),
            power_sensor_id: er.RegistryEntry(
                entity_id=power_sensor_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="powercalc",
                device_id=device_id,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: light_id},
        {},
    )

    energy_entity_entry = entity_reg.async_get(power_sensor_id)
    assert energy_entity_entry
    assert energy_entity_entry.device_id == device_id


async def test_setup_multiple_entities_in_single_platform_config(
    hass: HomeAssistant,
) -> None:
    await create_input_booleans(hass, ["test1", "test2", "test3"])

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
                get_simple_fixed_config("input_boolean.test2"),
                # Omitting the entity_id should log an error, but still successfully create the other entities
                {CONF_NAME: "test3", CONF_FIXED: {CONF_POWER: 20}},
            ],
        },
    )

    await hass.async_start()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test1_power")
    assert hass.states.get("sensor.test2_power")
    assert not hass.states.get("sensor.test3_power")


async def test_change_options_of_renamed_sensor(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id="abcdef",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy_daily").name == "test energy daily"

    entity_reg.async_update_entity(
        entity_id="sensor.test_energy_daily",
        name="Renamed daily utility meter",
    )
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.test_energy_daily").name
        == "Renamed daily utility meter"
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_CREATE_UTILITY_METERS: True, CONF_POWER: 100},
    )
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.test_energy_daily").name
        == "Renamed daily utility meter"
    )


async def test_renaming_sensor_is_retained_after_startup(
    hass: HomeAssistant,
    entity_reg: er.EntityRegistry,
) -> None:
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
    )
    await hass.async_block_till_done()
    entity_reg.async_update_entity(entity_id="sensor.test_power", name="Renamed power")
    await hass.async_block_till_done()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id="abcdef",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").name == "Renamed power"


async def test_sensors_with_errors_are_skipped_for_multiple_entity_setup(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    When creating a group or setting up multiple entities in one platform entry,
    a sensor with an error should be skipped and not prevent the whole group from being setup.
    This should be logged as an error.
    """
    caplog.set_level(logging.ERROR)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 40},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test2",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {},
                },
                {
                    CONF_ENTITIES: [
                        {
                            CONF_ENTITY_ID: "input_boolean.test3",
                            CONF_MODE: CalculationStrategy.FIXED,
                            CONF_FIXED: {},
                        },
                    ],
                },
            ],
        },
    )
    await hass.async_block_till_done()

    assert len(caplog.records) == 2
    assert "Skipping sensor setup" in caplog.text


async def test_create_config_entry_without_energy_sensor(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: "light.test",
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id="abcd",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testentry_power")
    assert not hass.states.get("sensor.testentry_energy")


async def test_rename_source_entity_id(hass: HomeAssistant) -> None:
    light_id = "sensor.my_light"
    entity_reg = mock_registry(
        hass,
        {
            light_id: er.RegistryEntry(
                entity_id=light_id,
                disabled_by=er.RegistryEntryDisabler.DEVICE,
                unique_id="1234",
                platform="light",
            ),
        },
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: light_id,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id="abcd",
    )
    entry.add_to_hass(hass)

    await run_powercalc_setup(
        hass,
        {},
    )

    new_light_id = "sensor.my_light_new"
    entity_reg.async_update_entity(entity_id=light_id, new_entity_id=new_light_id)
    await hass.async_block_till_done()

    changed_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert changed_entry.data.get(CONF_ENTITY_ID) == new_light_id

    hass.states.async_set(new_light_id, STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testentry_power")
    assert power_state.state == "50.00"
    assert power_state.attributes.get(ATTR_SOURCE_ENTITY) == new_light_id


async def test_change_config_entry_entity_id(hass: HomeAssistant) -> None:
    """Test that changing the source entity of an existing config entry works correctly"""

    original_light_id = "light.original"
    original_unique_id = "aaaa"
    new_light_id = "light.new"
    new_unique_id = "bbbb"
    mock_registry(
        hass,
        {
            original_light_id: er.RegistryEntry(
                entity_id=original_light_id,
                unique_id=original_unique_id,
                platform="light",
            ),
            new_light_id: er.RegistryEntry(
                entity_id=original_light_id,
                unique_id=new_unique_id,
                platform="light",
            ),
        },
    )

    # Create an existing config entry referencing the original source entity
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: original_light_id,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_UNIQUE_ID: original_unique_id,
        },
        unique_id=original_unique_id,
    )
    entry.add_to_hass(hass)

    await run_powercalc_setup(
        hass,
        {},
    )

    hass.states.async_set(original_light_id, STATE_ON)
    hass.states.async_set(new_light_id, STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testentry_power")
    assert power_state.attributes.get(ATTR_SOURCE_ENTITY) == original_light_id
    assert power_state.state == "50.00"

    # Change the entity_id using the options flow
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )
    user_input = {CONF_ENTITY_ID: new_light_id, CONF_POWER: 100}
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    await hass.async_block_till_done()

    changed_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert changed_entry.data.get(CONF_ENTITY_ID) == new_light_id
    assert changed_entry.unique_id == original_unique_id

    power_state = hass.states.get("sensor.testentry_power")
    assert power_state.attributes.get(ATTR_SOURCE_ENTITY) == new_light_id
    assert power_state.state == "100.00"
