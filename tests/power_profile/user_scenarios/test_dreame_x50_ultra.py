from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import CONF_ENTITY_ID, STATE_IDLE, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY
from tests.common import (
    assert_entity_state,
    get_test_profile_dir,
    mock_devices,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)


async def test_dreame_x50_ultra(hass: HomeAssistant) -> None:
    """Test all composite branches from the Dreame X50 Ultra profile.

    The profile uses `sum_all`, so branches are additive. Drying in particular
    runs on top of charging, and both contributions must be counted.

    See https://github.com/bramstroker/homeassistant-powercalc/pull/4547
    """
    device_id = "dreame-x50-ultra"
    vacuum_entity = "vacuum.dreame_x50_ultra"
    battery_entity = "sensor.dreame_x50_ultra_battery"
    status_entity = "sensor.dreame_x50_ultra_status"
    task_status_entity = "sensor.dreame_x50_ultra_task_status"
    auto_empty_status_entity = "sensor.dreame_x50_ultra_auto_empty_status"
    self_wash_base_status_entity = "sensor.dreame_x50_ultra_self_wash_base_status"
    charging_state_entity = "sensor.dreame_x50_ultra_charging_state"
    power_entity = "sensor.dreame_x50_ultra_power"

    mock_devices(hass, {device_id: {"manufacturer": "Dreame", "model": "X50 Ultra"}})
    mock_entities_in_registry(
        hass,
        {
            vacuum_entity: {"platform": "dreame_vacuum", "device_id": device_id},
            battery_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "device_class": SensorDeviceClass.BATTERY,
            },
            status_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "translation_key": "status",
            },
            task_status_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "translation_key": "task_status",
            },
            auto_empty_status_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "translation_key": "auto_empty_status",
            },
            self_wash_base_status_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "translation_key": "self_wash_base_status",
            },
            charging_state_entity: {
                "platform": "dreame_vacuum",
                "device_id": device_id,
                "translation_key": "charging_state",
            },
        },
    )
    await set_states(
        hass,
        [
            (vacuum_entity, VacuumActivity.DOCKED),
            (battery_entity, 50),
            (status_entity, "sleeping"),
            (task_status_entity, STATE_IDLE),
            (auto_empty_status_entity, STATE_IDLE),
            (self_wash_base_status_entity, STATE_IDLE),
            (charging_state_entity, STATE_OFF),
        ],
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_entity,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("dreame_x50_ultra"),
        },
    )

    # Station asleep, nothing running. Measured 5.28 W over 153 samples.
    assert_entity_state(hass, power_entity, "5.55")

    # Awake but idle on the dock, which it is for a while after every process.
    # Same draw, and the baseline must not fall through to zero here.
    await set_states(hass, [(status_entity, STATE_IDLE)])
    assert_entity_state(hass, power_entity, "5.55")

    # Charging at 50 percent. The calibrate curve is total station power and
    # already contains standby, so the baseline branch must not fire here.
    await set_states(hass, [(status_entity, "charging"), (charging_state_entity, STATE_ON)])
    assert_entity_state(hass, power_entity, "29.21")

    # Drying on top of charging. This is the case `stop_at_first` got wrong:
    # it dropped the charging contribution entirely.
    await set_states(hass, [(self_wash_base_status_entity, "drying")])
    assert_entity_state(hass, power_entity, "76.71")

    # Drying at full battery, charging tapered off. Measured 52.4 W.
    await set_states(hass, [(battery_entity, 100)])
    assert_entity_state(hass, power_entity, "53.27")

    # Drying with the robot asleep and no charging at all.
    await set_states(
        hass,
        [(status_entity, "sleeping"), (charging_state_entity, STATE_OFF)],
    )
    assert_entity_state(hass, power_entity, "53.05")

    # Hot wash at the end of a job. Charging is suspended while the heater runs,
    # verified by the battery holding still, so the curve must not be added.
    await set_states(
        hass,
        [
            (status_entity, "charging"),
            (charging_state_entity, STATE_ON),
            (self_wash_base_status_entity, "washing"),
        ],
    )
    assert_entity_state(hass, power_entity, "107.10")

    # Cold rinse during a running job. Same sensor value, one third the power.
    await set_states(hass, [(status_entity, "cleaning")])
    assert_entity_state(hass, power_entity, "29.50")

    # Refilling the clean water tank.
    await set_states(hass, [(self_wash_base_status_entity, "clean_add_water")])
    assert_entity_state(hass, power_entity, "18.50")

    # Emptying the dust bin.
    await set_states(
        hass,
        [
            (status_entity, "charging"),
            (self_wash_base_status_entity, STATE_IDLE),
            (auto_empty_status_entity, "active"),
        ],
    )
    assert_entity_state(hass, power_entity, "214.30")

    # Station self clean, the largest draw on the machine.
    await set_states(
        hass,
        [(auto_empty_status_entity, STATE_IDLE), (task_status_entity, "station_cleaning")],
    )
    assert_entity_state(hass, power_entity, "540.00")

    # Robot out cleaning, running on its own battery. The station idles at
    # 0.1 W, below what the meter resolves.
    await set_states(
        hass,
        [
            (vacuum_entity, VacuumActivity.CLEANING),
            (status_entity, "cleaning"),
            (task_status_entity, "cleaning"),
            (charging_state_entity, STATE_OFF),
        ],
    )
    assert_entity_state(hass, power_entity, "0.00")
