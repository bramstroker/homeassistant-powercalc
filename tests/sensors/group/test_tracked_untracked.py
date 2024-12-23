from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR, CONF_UTILITY_METER_TYPES
from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_MAIN_POWER_SENSOR,
    GroupType,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from custom_components.powercalc.sensors.group.custom import GroupedPowerSensor
from custom_components.powercalc.sensors.group.subtract import SubtractGroupSensor
from custom_components.powercalc.sensors.group.tracked_untracked import create_tracked_untracked_group_sensors
from custom_components.powercalc.sensors.utility_meter import VirtualUtilityMeter


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
