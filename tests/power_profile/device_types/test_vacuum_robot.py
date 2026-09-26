from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import CONF_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import (
    assert_entity_state,
    async_advance_time,
    get_test_profile_dir,
    mock_devices,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)


async def test_vacuum_robot(
    hass: HomeAssistant,
) -> None:
    """
    Test that vacuum can be setup from profile library
    """

    vacuum_id = "vacuum.roomba"
    battery_id = "sensor.roomba_battery"

    mock_entities_in_registry(
        hass,
        {
            vacuum_id: {"unique_id": "unique_vacuum_1", "platform": "test", "device_id": "device_1"},
            battery_id: {
                "unique_id": "unique_battery_1",
                "platform": "test",
                "device_id": "device_1",
                "device_class": "battery",
            },
        },
    )
    mock_devices(
        hass,
        {
            "device_1": {},
        },
    )

    power_sensor_id = "sensor.roomba_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("vacuum_robot"),
        },
    )

    assert_entity_state(hass, power_sensor_id, STATE_UNAVAILABLE)

    await set_states(hass, [(battery_id, 50), (vacuum_id, VacuumActivity.CLEANING)])
    assert_entity_state(hass, power_sensor_id, "0.00")

    await set_states(hass, [(battery_id, 0), (vacuum_id, VacuumActivity.DOCKED)])
    assert_entity_state(hass, power_sensor_id, "20.00")

    await set_states(hass, [(battery_id, 85), (vacuum_id, VacuumActivity.DOCKED)])
    assert_entity_state(hass, power_sensor_id, "15.00")

    await set_states(hass, [(battery_id, 100), (vacuum_id, VacuumActivity.DOCKED)])
    assert_entity_state(hass, power_sensor_id, "1.50")


async def test_vacuum_profile_tracks_dock_drying_switch(hass: HomeAssistant) -> None:
    """Synthetic charging and drying loads update independently across the two devices."""
    mock_devices(
        hass,
        {
            "robot": {"identifiers": {("roborock", "robot")}},
            "dock": {"identifiers": {("roborock", "robot_dock")}},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "vacuum.robot": {"platform": "roborock", "device_id": "robot"},
            "switch.dock_drying": {
                "platform": "roborock",
                "device_id": "dock",
                "translation_key": "mop_drying",
            },
        },
    )
    await set_states(hass, [("vacuum.robot", VacuumActivity.DOCKED), ("switch.dock_drying", "off")])

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "vacuum.robot",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("vacuum_dock"),
        },
    )

    assert_entity_state(hass, "sensor.robot_power", "30.00")
    await set_states(hass, [("switch.dock_drying", "on")])
    assert_entity_state(hass, "sensor.robot_power", "80.00")
    await set_states(hass, [("vacuum.robot", VacuumActivity.CLEANING)])
    assert_entity_state(hass, "sensor.robot_power", "50.00")
    await set_states(hass, [("switch.dock_drying", "off")])
    assert_entity_state(hass, "sensor.robot_power", "0.00")


async def test_with_tapering_playbook(hass: HomeAssistant) -> None:
    vacuum_id = "vacuum.roomba"
    battery_id = "sensor.roomba_battery"

    mock_entities_in_registry(
        hass,
        {
            vacuum_id: {"unique_id": "unique_vacuum_1", "platform": "test", "device_id": "device_1"},
            battery_id: {
                "unique_id": "unique_battery_1",
                "platform": "test",
                "device_id": "device_1",
                "device_class": "battery",
            },
        },
    )
    mock_devices(
        hass,
        {
            "device_1": {},
        },
    )

    power_sensor_id = "sensor.roomba_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("vacuum_robot_tapering"),
        },
    )

    await set_states(hass, [(battery_id, 30), (vacuum_id, VacuumActivity.DOCKED)])
    assert_entity_state(hass, power_sensor_id, "20.00")

    await set_states(hass, [(battery_id, 100), (vacuum_id, VacuumActivity.DOCKED)])
    assert_entity_state(hass, power_sensor_id, "0.00")

    await async_advance_time(hass, 1)

    assert_entity_state(hass, power_sensor_id, "9.00")

    await async_advance_time(hass, 3)

    assert_entity_state(hass, power_sensor_id, "5.00")

    await async_advance_time(hass, 5)

    assert_entity_state(hass, power_sensor_id, "3.00")

    await async_advance_time(hass, 60)

    assert_entity_state(hass, power_sensor_id, "3.00")
