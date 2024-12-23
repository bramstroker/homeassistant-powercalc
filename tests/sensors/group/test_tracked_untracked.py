from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_registry

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR, CONF_FIXED, CONF_UTILITY_METER_TYPES
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
from custom_components.powercalc.sensors.group.tracked_untracked import create_tracked_untracked_group_sensors
from custom_components.powercalc.sensors.utility_meter import VirtualUtilityMeter
from tests.common import run_powercalc_setup


async def test_main_power_is_removed_from_tracked_entities(hass: HomeAssistant) -> None:
    sensors = await create_tracked_untracked_group_sensors(
        hass,
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power", "sensor.main_power"],
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
        },
    )

    assert len(sensors) == 2
    tracked_sensor = sensors[0]
    assert isinstance(tracked_sensor, GroupedPowerSensor)
    assert tracked_sensor.entity_id == "sensor.tracked_power"
    assert tracked_sensor.entities == {"sensor.1_power", "sensor.2_power"}

    untracked_sensor = sensors[1]
    assert isinstance(untracked_sensor, SubtractGroupSensor)
    assert untracked_sensor.entity_id == "sensor.untracked_power"


async def test_energy_sensors_and_utility_meters_created(hass: HomeAssistant) -> None:
    sensors = await create_tracked_untracked_group_sensors(
        hass,
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
    mock_registry(
        hass,
        {
            "sensor.test1_power": RegistryEntry(
                entity_id="sensor.test1_power",
                name="Test1",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

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

    sensors = await create_tracked_untracked_group_sensors(
        hass,
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_AUTO: True,
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_CREATE_UTILITY_METERS: False,
        },
    )

    assert len(sensors) == 2
    tracked_sensor = sensors[0]
    assert isinstance(tracked_sensor, GroupedPowerSensor)
    assert tracked_sensor.entities == {"sensor.test1_power", "sensor.test3_power"}
