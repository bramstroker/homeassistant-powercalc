from homeassistant.components.lawn_mower import LawnMowerActivity
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
    Test that lawn mower can be setup from profile library
    """

    mower_id = "lawn_mower.mymower"
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

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: mower_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("lawn_mower"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(battery_id, 50)
    hass.states.async_set(mower_id, LawnMowerActivity.MOWING)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "11.55"

    hass.states.async_set(battery_id, 0)
    hass.states.async_set(mower_id, LawnMowerActivity.RETURNING)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "11.55"

    hass.states.async_set(battery_id, 85)
    hass.states.async_set(mower_id, LawnMowerActivity.DOCKED)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "63.35"

    hass.states.async_set(battery_id, 100)
    hass.states.async_set(mower_id, LawnMowerActivity.DOCKED)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "2.12"

    hass.states.async_set(battery_id, 100)
    hass.states.async_set(mower_id, LawnMowerActivity.MOWING)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "11.55"
