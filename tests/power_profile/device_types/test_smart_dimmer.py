from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.powercalc import CONF_IGNORE_UNAVAILABLE_STATE, async_setup_entry
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    DOMAIN,
)
from tests.common import get_test_config_dir, get_test_profile_dir, run_powercalc_setup
from tests.config_flow.common import confirm_auto_discovered_model, initialize_options_flow
from tests.conftest import MockEntityWithModel


async def test_smart_dimmer_power_input_yaml(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test a smart dimmer can be setup with YAML and a linear power value for the light provided by the user
    The values for standby power on and off should be taken from the power profile library.
    The linear power value from the user should be added to the total power consumption. standby_power_on + power
    """
    switch_id = "light.test"

    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer"),
            CONF_LINEAR: {CONF_MIN_POWER: 1.5, CONF_MAX_POWER: 50},
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    hass.states.async_set(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "50.50"

    hass.states.async_set(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 10})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "3.90"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.30"


async def test_smart_dimmer_power_input_yaml_omit_linear_config(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test a smart dimmer can be setup with YAML omitting the linear power value for the light
    """
    switch_id = "light.test"

    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer"),
        },
    )

    hass.states.async_set(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.50"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.30"


async def test_smart_dimmer_power_input_gui_config_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test a smart dimmer can be setup with GUI and a fixed power value for the light configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The linear power value from the user should be added to the total power consumption. standby_power_on + power
    """
    hass.config.config_dir = get_test_config_dir()
    light_entity_id = "light.test"
    manufacturer = "test"
    model = "smart_dimmer"

    mock_entity_with_model_information(
        entity_id=light_entity_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(hass, {})

    # Retrieve the discovery flow
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    flow = flows[0]

    assert flow["step_id"] == Step.LIBRARY
    result = await confirm_auto_discovered_model(hass, flow)

    # After confirming the manufacturer/model we must be directed to the linear config step
    assert result["step_id"] == Step.LINEAR
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_MIN_POWER: 2, CONF_MAX_POWER: 50},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LINEAR] == {CONF_MIN_POWER: 2, CONF_MAX_POWER: 50}

    await async_setup_entry(hass, result["result"])

    config_entry = result["result"]

    # Toggle the switch to different states and check for correct power values
    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "50.50"

    hass.states.async_set(light_entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.30"

    # Change the power value via the options
    result = await initialize_options_flow(hass, config_entry, Step.LINEAR)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_MIN_POWER: 4, CONF_MAX_POWER: 40},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Set the switch on again and see if it has the updated power value
    hass.states.async_set(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "40.50"
