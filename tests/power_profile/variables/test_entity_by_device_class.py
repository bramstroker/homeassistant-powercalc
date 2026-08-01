import logging

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
)
from tests.common import (
    assert_entity_state,
    get_test_profile_dir,
    mock_devices,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)


async def test_variable_replaced(hass: HomeAssistant) -> None:
    """Test entity_by_device_class variable works as expected"""

    mock_entities_in_registry(
        hass,
        {
            "switch.test": {"platform": "test", "device_id": "device_1"},
            "sensor.test": {"platform": "test", "device_id": "device_1", "device_class": "temperature"},
        },
    )
    mock_devices(
        hass,
        {
            "device_1": {},
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

    await set_states(hass, [("switch.test", STATE_ON), ("sensor.test", "20")])
    assert_entity_state(hass, "sensor.test_power", "10.00")

    await set_states(hass, [("sensor.test", "19")])
    assert_entity_state(hass, "sensor.test_power", "0.00")


async def test_exception_raised_when_entity_not_found(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test LibraryError is raised when entity with device class cannot be found"""

    caplog.set_level(logging.ERROR)

    mock_entities_in_registry(
        hass,
        {
            "switch.test": {"platform": "test", "device_id": "device_1"},
        },
    )
    mock_devices(
        hass,
        {
            "device_1": {},
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
