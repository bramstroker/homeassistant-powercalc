import os

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_ENTITY_ID, STATE_ON, STATE_OFF

from homeassistant.helpers.device_registry import DeviceRegistry, DeviceEntry
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_registry, mock_device_registry

from tests.common import run_powercalc_setup_yaml_config

from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL, CONF_CUSTOM_MODEL_DIRECTORY


async def test_smart_switch(hass: HomeAssistant):
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
                id="shelly-device-id",
                manufacturer=manufacturer,
                model=model
            )
        }
    )

    power_sensor_id = "sensor.oven_device_power"

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_switch")
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


def get_test_profile_dir(sub_dir: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), "../../testing_config/powercalc_profiles", sub_dir
    )
