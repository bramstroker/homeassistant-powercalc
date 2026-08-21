from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc import CONF_SENSOR_TYPE
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    get_test_profile_dir,
    mock_device,
    run_powercalc_setup,
    set_states,
)


@pytest.mark.parametrize(
    "profile_dir,power_sensor_id",
    [
        ("power_meter", "sensor.pm_mini_device_power"),
        # The legacy profile has no `only_self_usage`, so the sensors use the regular naming.
        ("power_meter_legacy", "sensor.pm_mini_power"),
    ],
)
async def test_power_meter(hass: HomeAssistant, profile_dir: str, power_sensor_id: str) -> None:
    """Test that a power meter can be setup from the profile library, in both profile formats"""
    sensor_id = "sensor.pm_mini"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: sensor_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir(profile_dir),
        },
    )

    await set_states(hass, [(sensor_id, "50.00")])
    assert_entity_state(hass, power_sensor_id, "0.30")


async def test_per_device_discovery_from_gui(hass: HomeAssistant) -> None:
    mock_device(hass, "f52deed323f1ca5c11d90486e55b6eff", "shelly", "shelly pm mini gen3")

    await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_UNIQUE_ID: "pc_f52deed323f1ca5c11d90486e55b6eff",
            CONF_MANUFACTURER: "shelly",
            CONF_MODEL: "shelly pm mini gen3",
            CONF_AVAILABILITY_ENTITY: "sensor.some_entity",
            CONF_SENSOR_TYPE: "virtual_power",
            CONF_NAME: "Test",
            CONF_DEVICE: "f52deed323f1ca5c11d90486e55b6eff",
        },
        setup=False,
    )

    await set_states(hass, [("sensor.some_entity", "50.00")])
    await run_powercalc_setup(hass)

    assert_entity_state(hass, "sensor.test_device_power", "0.64")
