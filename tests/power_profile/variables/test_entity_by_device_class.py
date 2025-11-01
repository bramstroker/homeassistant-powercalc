import logging

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
import pytest
from pytest_homeassistant_custom_component.common import (
    RegistryEntryWithDefaults,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import get_test_profile_dir, run_powercalc_setup


async def test_variable_replaced(hass: HomeAssistant) -> None:
    """Test entity_by_device_class variable works as expected"""

    mock_registry(
        hass,
        {
            "switch.test": RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id="1111",
                platform="test",
                device_id="device_1",
            ),
            "sensor.test": RegistryEntryWithDefaults(
                entity_id="sensor.test",
                unique_id="2222",
                platform="test",
                device_id="device_1",
                device_class="temperature",
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
            CONF_ENTITY_ID: "switch.test",
            CONF_NAME: "Test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("device_class_variable"),
        },
    )

    hass.states.async_set("switch.test", STATE_ON)
    hass.states.async_set("sensor.test", "20")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"

    hass.states.async_set("sensor.test", "19")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"


async def test_exception_raised_when_entity_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test LibraryError is raised when entity with device class cannot be found"""

    caplog.set_level(logging.ERROR)

    mock_registry(
        hass,
        {
            "switch.test": RegistryEntryWithDefaults(
                entity_id="switch.test",
                unique_id="1111",
                platform="test",
                device_id="device_1",
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
            CONF_ENTITY_ID: "switch.test",
            CONF_NAME: "Test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("device_class_variable"),
        },
    )

    assert "Could not find related entity for device class temperature of entity switch.test" in caplog.text
