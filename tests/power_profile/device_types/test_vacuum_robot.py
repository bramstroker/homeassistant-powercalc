from homeassistant.components.vacuum import STATE_CLEANING, STATE_DOCKED
from homeassistant.const import CONF_ENTITY_ID
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
from tests.common import get_test_profile_dir, run_powercalc_setup


async def test_vacuum_robot(
    hass: HomeAssistant,
) -> None:
    """
    Test that vacuum can be setup from profile library
    """

    vacuum_id = "vacuum.roomba"
    battery_id = "sensor.roomba_battery"

    mock_registry(
        hass,
        {
            vacuum_id: RegistryEntryWithDefaults(
                entity_id=vacuum_id,
                unique_id="unique_vacuum_1",
                platform="test",
                device_id="device_1",
            ),
            battery_id: RegistryEntryWithDefaults(
                entity_id=battery_id,
                unique_id="unique_battery_1",
                platform="test",
                device_id="device_1",
                device_class="battery",
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

    power_sensor_id = "sensor.roomba_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("vacuum_robot"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(battery_id, 50)
    hass.states.async_set(vacuum_id, STATE_CLEANING)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.00"

    hass.states.async_set(battery_id, 0)
    hass.states.async_set(vacuum_id, STATE_DOCKED)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "20.00"

    hass.states.async_set(battery_id, 85)
    hass.states.async_set(vacuum_id, STATE_DOCKED)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "15.00"

    hass.states.async_set(battery_id, 100)
    hass.states.async_set(vacuum_id, STATE_DOCKED)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "1.50"
