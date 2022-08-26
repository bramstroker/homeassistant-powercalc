import logging

import pytest
from homeassistant.components import light
from homeassistant.components.integration.sensor import ATTR_SOURCE_ID
from homeassistant.components.light import ColorMode
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
    ENERGY_KILO_WATT_HOUR,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.test.light as test_light_platform
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENTITIES,
    ATTR_SOURCE_ENTITY,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_GROUP,
    CONF_INCLUDE,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight

from .common import (
    create_discoverable_light,
    create_input_boolean,
    create_input_booleans,
    create_mock_light_entity,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config,
)


async def test_fixed_power_sensor_from_yaml(hass: HomeAssistant):
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
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
        energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR
    )
    assert energy_state.attributes.get(ATTR_SOURCE_ID) == "sensor.test_power"
    assert energy_state.attributes.get(ATTR_SOURCE_ENTITY) == "input_boolean.test"


async def test_utility_meter_is_created(hass: HomeAssistant):
    """Test that utility meters are succesfully created when `create_utility_meter: true`"""
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
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


async def test_create_nested_group_sensor(hass: HomeAssistant):
    await create_input_booleans(hass, ["test", "test1", "test2"])

    await run_powercalc_setup_yaml_config(
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

    hass.states.async_set("input_boolean.test2", STATE_OFF)
    await hass.async_block_till_done()

    group1 = hass.states.get("sensor.testgroup1_power")
    assert group1.state == "100.00"

    group2 = hass.states.get("sensor.testgroup2_power")
    assert group2.state == "0.00"


async def test_light_lut_strategy(hass: HomeAssistant):
    light_entity = test_light_platform.MockLight(
        "test1",
        STATE_ON,
        unique_id="dsafbwq",
    )
    light_entity.supported_color_modes = {light.ColorMode.BRIGHTNESS}
    light_entity.color_mode = light.ColorMode.BRIGHTNESS
    light_entity.brightness = 125
    light_entity.manufacturer = "signify"
    light_entity.model = "LWB010"

    (light_entity_id, __) = await create_mock_light_entity(hass, light_entity)

    await run_powercalc_setup_yaml_config(
        hass, {CONF_PLATFORM: DOMAIN, CONF_ENTITY_ID: light_entity_id}
    )

    state = hass.states.get("sensor.test1_power")
    assert state
    assert state.state == "2.67"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER
    assert state.attributes.get(ATTR_CALCULATION_MODE) == CalculationStrategy.LUT
    assert state.attributes.get(ATTR_SOURCE_ENTITY) == light_entity_id


async def test_error_when_configuring_same_entity_twice(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        [
            get_simple_fixed_config("input_boolean.test", 50),
            get_simple_fixed_config("input_boolean.test", 100),
        ],
    )

    assert "This entity has already configured a power sensor" in caplog.text
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_alternate_naming_strategy(hass: HomeAssistant):
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        [
            get_simple_fixed_config("input_boolean.test", 50),
        ],
        {
            CONF_POWER_SENSOR_NAMING: "{} Power consumption",
            CONF_POWER_SENSOR_FRIENDLY_NAMING: "{} Power friendly",
            CONF_ENERGY_SENSOR_NAMING: "{} Energy kwh",
            CONF_ENERGY_SENSOR_FRIENDLY_NAMING: "{} Energy friendly",
        },
    )

    power_state = hass.states.get("sensor.test_power_consumption")
    assert power_state
    assert power_state.attributes.get(ATTR_FRIENDLY_NAME) == "test Power friendly"
    energy_state = hass.states.get("sensor.test_energy_kwh")
    assert energy_state
    assert energy_state.attributes.get(ATTR_FRIENDLY_NAME) == "test Energy friendly"


async def test_can_create_same_entity_twice_with_unique_id(hass: HomeAssistant):
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
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
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    light = test_light_platform.MockLight("test", STATE_ON)
    light.manufacturer = "lidl"
    light.model = "non_existing_model"

    await create_mock_light_entity(hass, light)

    # Run powercalc setup with autodiscovery
    await run_powercalc_setup_yaml_config(hass, {}, {})

    assert "Model not found in library, skipping auto configuration" in caplog.text


async def test_can_include_autodiscovered_entity_in_group(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    """Test that models are automatically discovered and power sensors created"""

    caplog.set_level(logging.ERROR)

    await create_mock_light_entity(hass, create_discoverable_light("testa"))

    hass.states.async_set(
        "light.testa", STATE_ON, {"brightness": 125, "color_mode": ColorMode.BRIGHTNESS}
    )
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
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


async def test_include_area(
    hass: HomeAssistant, entity_reg: EntityRegistry, area_reg: AreaRegistry
):
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area = area_reg.async_get_or_create("Bathroom 1")
    await hass.async_block_till_done()
    entity_reg.async_update_entity("light.bathroom_mirror", area_id=area.id)
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {CONF_CREATE_GROUP: "Test include", CONF_INCLUDE: {CONF_AREA: "bathroom_1"}},
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_mirror_power"}

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "Test include area by name",
            CONF_INCLUDE: {CONF_AREA: "Bathroom 1"},
        },
    )

    assert hass.states.get("sensor.test_include_area_by_name_power")


async def test_include_area_not_found(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "Test area not found",
            CONF_INCLUDE: {CONF_AREA: "hallway"},
        },
    )
    assert "No area with id or name" in caplog.text


async def test_include_light_group(hass: HomeAssistant):
    discoverable_light = create_discoverable_light("bathroom_mirror")
    non_discoverable_light = MockLight("bathroom_spots")

    await create_mock_light_entity(hass, [discoverable_light, non_discoverable_light])

    # Ugly hack, maybe I can figure out something better in the future.
    # Light domain is already setup for platform test, remove the component so we can setup light group
    if light.DOMAIN in hass.config.components:
        hass.config.components.remove(light.DOMAIN)

    await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: {
                "platform": "group",
                "name": "Bathroom",
                "entities": ["light.bathroom_mirror", "light.bathroom_spots"],
            }
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "Test include lightgroup",
            CONF_INCLUDE: {CONF_GROUP: "light.bathroom"},
        },
    )

    await hass.async_start()
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.test_include_lightgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_mirror_power"}


async def test_user_can_rename_entity_id(
    hass: HomeAssistant, entity_reg: EntityRegistry
):
    """
    When the power/energy sensors exist already with an unique ID, don't change the entity ID
    This allows the users to change the entity ID's from the GUI
    """
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef", suggested_object_id="my_renamed_power"
    )
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef_energy", suggested_object_id="my_renamed_energy"
    )
    await hass.async_block_till_done()

    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
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
    hass: HomeAssistant, entity_reg: EntityRegistry, device_reg: DeviceRegistry
):
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


async def test_setup_multiple_entities_in_single_platform_config(hass: HomeAssistant):
    await create_input_booleans(hass, ["test1", "test2", "test3"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
                get_simple_fixed_config("input_boolean.test2"),
                # Omitting the entity_id should log an error, but still successfully create the other entities
                {CONF_NAME: "test3", CONF_FIXED: {CONF_POWER: 20}},
            ]
        },
    )

    await hass.async_start()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test1_power")
    assert hass.states.get("sensor.test2_power")
    assert not hass.states.get("sensor.test3_power")


async def test_change_options_of_renamed_sensor(hass: HomeAssistant, entity_reg: EntityRegistry):
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

    entity_reg.async_update_entity(entity_id="sensor.test_energy_daily", name="Renamed daily utility meter")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy_daily").name == "Renamed daily utility meter"

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CREATE_UTILITY_METERS: True,
            CONF_POWER: 100
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy_daily").name == "Renamed daily utility meter"


async def test_renaming_sensor_is_retained_after_startup(hass: HomeAssistant, entity_reg: EntityRegistry):
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef", suggested_object_id="test_power"
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

