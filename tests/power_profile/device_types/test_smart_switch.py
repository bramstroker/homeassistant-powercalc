from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.powercalc.config_flow import CONF_CONFIRM_AUTODISCOVERED_MODEL
from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    DOMAIN,
)
from tests.common import get_test_profile_dir, run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_smart_switch(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test that smart plug can be setup from profile library
    """
    switch_id = "switch.oven"
    manufacturer = "Shelly"
    model = "Shelly Plug S"

    mock_entity_with_model_information(
        entity_id=switch_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.oven_device_power"

    await run_powercalc_setup(
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


async def test_smart_switch_power_input_yaml(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test a smart switch can be setup with YAML and a fixed power value for the appliance configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The fixed power value from the user should be added to the total power consumption. standby_power_on + power
    """
    switch_id = "switch.heater"
    manufacturer = "IKEA"
    model = "Smart Control Outlet"

    mock_entity_with_model_information(
        entity_id=switch_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.heater_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: switch_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_switch"),
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "50.82"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.52"


async def test_smart_switch_power_input_gui_config_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test a smart switch can be setup with GUI and a fixed power value for the appliance configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The fixed power value from the user should be added to the total power consumption. standby_power_on + power
    """
    switch_id = "switch.heater"
    manufacturer = "IKEA"
    model = "TRADFRI control outlet"

    mock_entity_with_model_information(
        entity_id=switch_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.heater_device_power"

    await run_powercalc_setup(hass, {})

    # Retrieve the discovery flow
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    flow = flows[0]

    assert flow["step_id"] == "library"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    # After confirming the manufacturer/model we must be directed to the fixed config step
    assert result["step_id"] == "fixed"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_POWER: 50},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    config_entry = entries[0]

    # Toggle the switch to different states and check for correct power values
    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "50.80"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.40"

    # Change the power value via the options
    result = await hass.config_entries.options.async_init(
        config_entry.entry_id,
        data=None,
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_POWER: 100},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Set the switch on again and see if it has the updated power value
    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "100.80"


async def test_hue_smart_plug_is_discovered(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        entity_id="switch.smartplug",
        manufacturer="signify",
        model="LOM002",
        platform="hue",
        unique_id="1234",
    )
    await run_powercalc_setup(hass, {})

    assert hass.states.get("sensor.smartplug_device_power")
