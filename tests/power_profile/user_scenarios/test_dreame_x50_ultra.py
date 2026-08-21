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

    See https://github.com/bramstroker/homeassistant-powercalc/pull/4547
    """
    device_id = "dreame-x50-ultra"
    vacuum_entity = "vacuum.dreame_x50_ultra"
    battery_entity = "sensor.dreame_x50_ultra_battery"
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
    assert_entity_state(hass, power_entity, "5.55")

    await set_states(hass, [(task_status_entity, "station_cleaning")])
    assert_entity_state(hass, power_entity, "559.10")

    await set_states(hass, [(task_status_entity, "idle"), (auto_empty_status_entity, "active")])
    assert_entity_state(hass, power_entity, "225.00")

    await set_states(
        hass,
        [(auto_empty_status_entity, "idle"), (self_wash_base_status_entity, "washing")],
    )
    assert_entity_state(hass, power_entity, "107.80")

    await set_states(hass, [(self_wash_base_status_entity, "drying")])
    assert_entity_state(hass, power_entity, "54.90")

    await set_states(hass, [(charging_state_entity, STATE_ON)])
    assert_entity_state(hass, power_entity, "54.90")

    await set_states(hass, [(self_wash_base_status_entity, "idle")])
    assert_entity_state(hass, power_entity, "34.76")

    await set_states(hass, [(battery_entity, 100)])
    assert_entity_state(hass, power_entity, "11.32")

    await set_states(hass, [(vacuum_entity, VacuumActivity.CLEANING)])
    assert_entity_state(hass, power_entity, "5.55")
