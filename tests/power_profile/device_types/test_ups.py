from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_VARIABLES
from tests.common import assert_entity_state, get_test_profile_dir, run_powercalc_setup, set_states


async def test_ups_power_at_various_loads(hass: HomeAssistant) -> None:
    """Test UPS power calculation at various load levels."""
    load_entity = "sensor.ups_load"
    entity_id = "sensor.ups_output"

    await set_states(hass, [(entity_id, "50"), (load_entity, "50")])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_NAME: "UPS",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("ups"),
            CONF_VARIABLES: {
                "load_entity": load_entity,
                "nominal_va": 1500,
                "power_factor": 0.6,
            },
        },
    )

    # 50% load * 1500 VA * 0.6 PF / 100 = 450W
    assert_entity_state(hass, "sensor.ups_power", "450.00")

    # Test 0% load
    await set_states(hass, [(load_entity, "0")])
    assert_entity_state(hass, "sensor.ups_power", "0.00")

    # Test 100% load
    await set_states(hass, [(load_entity, "100")])
    # 100% * 1500 * 0.6 / 100 = 900W
    assert_entity_state(hass, "sensor.ups_power", "900.00")

    # Test 10% load
    await set_states(hass, [(load_entity, "10")])
    # 10% * 1500 * 0.6 / 100 = 90W
    assert_entity_state(hass, "sensor.ups_power", "90.00")


async def test_ups_with_unity_power_factor(hass: HomeAssistant) -> None:
    """Test UPS power calculation with power factor of 1.0 (resistive load)."""
    load_entity = "sensor.ups_load"
    entity_id = "sensor.ups_output"

    await set_states(hass, [(entity_id, "25"), (load_entity, "25")])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_NAME: "UPS",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("ups"),
            CONF_VARIABLES: {
                "load_entity": load_entity,
                "nominal_va": 1000,
                "power_factor": 1.0,
            },
        },
    )

    # 25% * 1000 VA * 1.0 PF / 100 = 250W
    assert_entity_state(hass, "sensor.ups_power", "250.00")
