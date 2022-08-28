import os

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_ENTITY_ID, STATE_ON, STATE_OFF

from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.common import run_powercalc_setup_yaml_config

from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL, CONF_CUSTOM_MODEL_DIRECTORY


async def test_smart_switch(hass: HomeAssistant, entity_reg: EntityRegistry, device_reg: DeviceRegistry):
    # Create a device
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", "abcdef")},
        manufacturer="Shelly",
        model="Shelly Plug S",
    )

    # Create a source entity which is bound to the device
    unique_id = "34445329342797234"
    entity_reg.async_get_or_create(
        "switch",
        "switch",
        unique_id,
        suggested_object_id="oven",
        device_id=device_entry.id,
    )
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_ENTITY_ID: "switch.oven",
            CONF_MANUFACTURER: "Shelly",
            CONF_MODEL: "Shelly Plug S",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_switch")
        },
    )

    power_state = hass.states.get("sensor.oven_device_power")
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set("switch.oven", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.oven_device_power").state == "0.82"

    hass.states.async_set("switch.oven", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.oven_device_power").state == "0.52"


def get_test_profile_dir(sub_dir: str) -> str:
    """@todo, create pytest fixture"""
    return os.path.join(
        os.path.dirname(__file__), "../../testing_config/powercalc_profiles", sub_dir
    )
