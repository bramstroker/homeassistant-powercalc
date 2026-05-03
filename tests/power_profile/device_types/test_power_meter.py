from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_device_registry

from custom_components.powercalc import CONF_SENSOR_TYPE, DOMAIN
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup, set_states
from tests.conftest import MockEntityWithModel


async def test_power_meter(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    sensor_id = "sensor.pm_mini"
    power_sensor_id = "sensor.pm_mini_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: sensor_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("power_meter"),
        },
    )

    await set_states(hass, [(sensor_id, "50.00")])
    assert_entity_state(hass, power_sensor_id, "0.30")


async def test_power_meter_legacy(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that multi switch can be setup from profile library
    """
    sensor_id = "sensor.pm_mini"
    power_sensor_id = "sensor.pm_mini_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: sensor_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("power_meter_legacy"),
        },
    )

    await set_states(hass, [(sensor_id, "50.00")])
    assert_entity_state(hass, power_sensor_id, "0.30")


async def test_per_device_discovery_from_gui(hass: HomeAssistant) -> None:
    mock_device_registry(
        hass,
        {
            "f52deed323f1ca5c11d90486e55b6eff": DeviceEntry(
                id="f52deed323f1ca5c11d90486e55b6eff",
                manufacturer="shelly",
                model="shelly pm mini gen3",
            ),
        },
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_UNIQUE_ID: "pc_f52deed323f1ca5c11d90486e55b6eff",
            CONF_MANUFACTURER: "shelly",
            CONF_MODEL: "shelly pm mini gen3",
            CONF_AVAILABILITY_ENTITY: "sensor.some_entity",
            CONF_SENSOR_TYPE: "virtual_power",
            CONF_NAME: "Test",
            CONF_DEVICE: "f52deed323f1ca5c11d90486e55b6eff",
        },
        unique_id="pc_f52deed323f1ca5c11d90486e55b6eff",
    )
    entry.add_to_hass(hass)

    await set_states(hass, [("sensor.some_entity", "50.00")])
    await run_powercalc_setup(hass)

    assert_entity_state(hass, "sensor.test_device_power", "0.64")
