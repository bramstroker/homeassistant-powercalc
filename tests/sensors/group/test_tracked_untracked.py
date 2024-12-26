from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR, CONF_FIXED, CONF_UTILITY_METER_TYPES, DATA_GROUP_ENTITIES
from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_GROUP_TRACKED_AUTO,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_MAIN_POWER_SENSOR,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    DUMMY_ENTITY_ID,
    GroupType,
    SensorType,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.group.tracked_untracked import TrackedPowerSensorFactory
from custom_components.powercalc.sensors.utility_meter import VirtualUtilityMeter
from tests.common import mock_sensors_in_registry, run_powercalc_setup
from tests.config_flow.common import create_mock_entry


async def test_main_power_is_removed_from_tracked_entities(hass: HomeAssistant) -> None:
    factory = TrackedPowerSensorFactory(
        hass,
        MockConfigEntry(),
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power", "sensor.main_power"],
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
        },
    )
    sensors = await factory.create_tracked_untracked_group_sensors()

    assert len(sensors) == 2
    tracked_sensor = sensors[0]
    assert isinstance(tracked_sensor, GroupedPowerSensor)
    assert tracked_sensor.entity_id == "sensor.tracked_power"
    assert tracked_sensor.entities == {"sensor.1_power", "sensor.2_power"}

    untracked_sensor = sensors[1]
    assert isinstance(untracked_sensor, SubtractGroupSensor)
    assert untracked_sensor.entity_id == "sensor.untracked_power"


async def test_energy_sensors_and_utility_meters_created(hass: HomeAssistant) -> None:
    factory = TrackedPowerSensorFactory(
        hass,
        MockConfigEntry(),
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power", "sensor.main_power"],
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: ["daily"],
        },
    )
    sensors = await factory.create_tracked_untracked_group_sensors()

    assert len(sensors) == 6
    assert isinstance(sensors[0], GroupedPowerSensor)
    assert sensors[0].entity_id == "sensor.tracked_power"
    assert isinstance(sensors[1], VirtualEnergySensor)
    assert sensors[1].entity_id == "sensor.tracked_energy"
    assert isinstance(sensors[2], VirtualUtilityMeter)
    assert sensors[2].entity_id == "sensor.tracked_energy_daily"
    assert isinstance(sensors[3], GroupedPowerSensor)
    assert sensors[3].entity_id == "sensor.untracked_power"
    assert isinstance(sensors[4], VirtualEnergySensor)
    assert sensors[4].entity_id == "sensor.untracked_energy"
    assert isinstance(sensors[5], VirtualUtilityMeter)
    assert sensors[5].entity_id == "sensor.untracked_energy_daily"


async def test_auto_tracking_entities(hass: HomeAssistant) -> None:
    """Test both entities from powercalc and other HA power entities are added."""
    mock_sensors_in_registry(hass, ["sensor.test1_power"])

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="2222",
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "Test2",
        },
        title="Test2",
    )
    config_entry.add_to_hass(hass)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="3333",
        data={
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "Test3",
            CONF_FIXED: {CONF_POWER: 10},
        },
        title="Test3",
    )
    config_entry.add_to_hass(hass)

    await run_powercalc_setup(hass)

    factory = TrackedPowerSensorFactory(
        hass,
        MockConfigEntry(),
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_AUTO: True,
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_CREATE_UTILITY_METERS: False,
        },
    )
    entities = await factory.get_tracked_power_entities()
    assert entities == {"sensor.test1_power", "sensor.test3_power"}


async def test_entity_registry_updates(hass: HomeAssistant) -> None:
    """Test that the tracked power sensor is updated when power sensors are added or removed to the system"""
    mock_sensors_in_registry(
        hass,
        ["sensor.test1_power", "sensor.test2_power", "sensor.test3_power"],
        ["sensor.test1_energy"],
    )
    entity_registry = er.async_get(hass)
    create_mock_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_NAME: "Tracked / Untracked",
            CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
            CONF_GROUP_TRACKED_AUTO: True,
        },
    )
    await run_powercalc_setup(hass)

    hass.states.async_set("sensor.test1_power", "10")
    hass.states.async_set("sensor.test2_power", "5")
    hass.states.async_set("sensor.test3_power", "10")
    await hass.async_block_till_done()

    tracked_power_sensor = hass.data[DOMAIN][DATA_GROUP_ENTITIES]["sensor.tracked_power"]
    assert tracked_power_sensor.entities == {"sensor.test1_power", "sensor.test2_power", "sensor.test3_power"}
    assert hass.states.get("sensor.tracked_power").state == "25.00"

    # Remove one of the tracked entities from registry
    entity_registry.async_remove("sensor.test2_power")
    entity_registry.async_remove("sensor.test1_energy")  # for coverage
    # Change the entity_id of one of the tracked entities
    entity_registry.async_update_entity("sensor.test1_power", new_entity_id="sensor.test1_power_new")
    entity_registry.async_update_entity("sensor.test3_power", icon="mdi:power")  # irrelevant change for coverage

    tracked_power_sensor = hass.data[DOMAIN][DATA_GROUP_ENTITIES]["sensor.tracked_power"]
    assert tracked_power_sensor.entities == {"sensor.test1_power_new", "sensor.test3_power"}
    assert hass.states.get("sensor.tracked_power").state == "10.00"

    # Add a new power entity to registry
    entity_registry.async_get_or_create(
        "sensor",
        "sensor",
        "aaa",
        suggested_object_id="test4_power",
        original_device_class=SensorDeviceClass.POWER,
    )

    tracked_power_sensor = hass.data[DOMAIN][DATA_GROUP_ENTITIES]["sensor.tracked_power"]
    assert tracked_power_sensor.entities == {"sensor.test1_power_new", "sensor.test3_power", "sensor.test4_power"}
    assert hass.states.get("sensor.tracked_power").state == "10.00"
