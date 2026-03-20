from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_VARIABLES
from tests.common import get_test_profile_dir, run_powercalc_setup


async def test_ups_power_at_various_loads(hass: HomeAssistant) -> None:
    """Test UPS power calculation at various load levels."""
    load_entity = "sensor.ups_load"
    entity_id = "sensor.ups_output"

    hass.states.async_set(entity_id, "50")
    hass.states.async_set(load_entity, "50")
    await hass.async_block_till_done()

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

    power_state = hass.states.get("sensor.ups_power")
    assert power_state
    # 50% load * 1500 VA * 0.6 PF / 100 = 450W
    assert power_state.state == "450.00"

    # Test 0% load
    hass.states.async_set(load_entity, "0")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ups_power").state == "0.00"

    # Test 100% load
    hass.states.async_set(load_entity, "100")
    await hass.async_block_till_done()
    # 100% * 1500 * 0.6 / 100 = 900W
    assert hass.states.get("sensor.ups_power").state == "900.00"

    # Test 10% load
    hass.states.async_set(load_entity, "10")
    await hass.async_block_till_done()
    # 10% * 1500 * 0.6 / 100 = 90W
    assert hass.states.get("sensor.ups_power").state == "90.00"


async def test_ups_with_unity_power_factor(hass: HomeAssistant) -> None:
    """Test UPS power calculation with power factor of 1.0 (resistive load)."""
    load_entity = "sensor.ups_load"
    entity_id = "sensor.ups_output"

    hass.states.async_set(entity_id, "25")
    hass.states.async_set(load_entity, "25")
    await hass.async_block_till_done()

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
    assert hass.states.get("sensor.ups_power").state == "250.00"
