import os

from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import get_test_profile_dir, run_powercalc_setup_yaml_config


async def test_smart_switch(hass: HomeAssistant):
    """
    Test that smart plug can be setup from profile library
    """
    switch_id = "switch.oven"
    manufacturer = "Shelly"
    model = "Shelly Plug S"

    mock_registry(
        hass,
        {
            switch_id: RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id="shelly-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "shelly-device": DeviceEntry(
                id="shelly-device-id", manufacturer=manufacturer, model=model
            )
        },
    )

    power_sensor_id = "sensor.oven_device_power"

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_switch"),
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.82"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.52"
