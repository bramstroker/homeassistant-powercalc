from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import (
    RegistryEntryWithDefaults,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup, set_states


async def test_lawn_mower(
    hass: HomeAssistant,
) -> None:
    """
    Test that lawn mower can be setup from profile library
    """

    mower_id = "lawn_mower.mymower"
    charging_id = "binary_sensor.mymower_charging"
    battery_id = "sensor.mymower_battery"
    power_sensor_id = "sensor.mymower_power"

    mock_registry(
        hass,
        {
            mower_id: RegistryEntryWithDefaults(
                entity_id=mower_id,
                unique_id="unique_mower_1",
                platform="test",
                device_id="device_1",
            ),
            battery_id: RegistryEntryWithDefaults(
                entity_id=battery_id,
                unique_id="unique_battery_1",
                platform="test",
                device_id="device_1",
                device_class=SensorDeviceClass.BATTERY,
            ),
            charging_id: RegistryEntryWithDefaults(
                entity_id=charging_id,
                unique_id="unique_charging_1",
                platform="test",
                device_id="device_1",
                device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "device_1": DeviceEntry(
                id="device_1",
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: mower_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("lawn_mower"),
        },
    )

    assert_entity_state(hass, power_sensor_id, STATE_UNAVAILABLE)

    await set_states(hass, [(battery_id, 50), (mower_id, LawnMowerActivity.MOWING), (charging_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "11.55")

    await set_states(hass, [(battery_id, 0), (mower_id, LawnMowerActivity.RETURNING), (charging_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "11.55")

    await set_states(hass, [(battery_id, 85), (mower_id, LawnMowerActivity.DOCKED), (charging_id, STATE_ON)])
    assert_entity_state(hass, power_sensor_id, "63.35")

    await set_states(hass, [(battery_id, 100), (mower_id, LawnMowerActivity.DOCKED), (charging_id, STATE_ON)])
    assert_entity_state(hass, power_sensor_id, "2.12")

    await set_states(hass, [(battery_id, 100), (mower_id, LawnMowerActivity.PAUSED), (charging_id, STATE_ON)])
    assert_entity_state(hass, power_sensor_id, "2.12")

    await set_states(hass, [(battery_id, 100), (mower_id, LawnMowerActivity.MOWING), (charging_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "11.55")
