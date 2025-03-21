from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType

from custom_components.powercalc import async_setup_entry
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    DOMAIN,
)
from tests.common import get_test_config_dir, get_test_profile_dir, run_powercalc_setup
from tests.config_flow.common import confirm_auto_discovered_model, initialize_options_flow
from tests.conftest import MockEntityWithModel


async def test_smart_switch_with_yaml(
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

    power_sensor_id = "sensor.oven_power"

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

    power_sensor_id = "sensor.heater_power"

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


async def test_gui_smart_switch_without_builtin_powermeter(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test setting up smart switch with relay, but without a built-in powermeter
    """
    hass.config.config_dir = get_test_config_dir()
    switch_id = "switch.heater"
    power_sensor_id = "sensor.heater_power"

    result = await start_discovery_flow(
        hass,
        mock_entity_with_model_information,
        switch_id,
        manufacturer="test",
        model="smart_switch_without_pm",
    )

    # After confirming the manufacturer/model we must be directed to the fixed config step
    assert result["step_id"] == Step.SMART_SWITCH
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_POWER: 50},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    await async_setup_entry(hass, result["result"])

    config_entry = result["result"]

    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "50.70"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.30"

    # Change the power value via the options
    result = await initialize_options_flow(hass, config_entry, Step.FIXED)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_POWER: 100},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Set the switch on again and see if it has the updated power value
    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "100.70"


async def test_gui_smart_switch_with_builtin_powermeter(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Test setting up smart switch with relay, but with a built-in powermeter
    """
    hass.config.config_dir = get_test_config_dir()
    switch_id = "switch.heater"
    power_sensor_id = "sensor.heater_device_power"

    result = await start_discovery_flow(
        hass,
        mock_entity_with_model_information,
        switch_id,
        manufacturer="test",
        model="smart_switch_with_pm",
    )

    # After confirming the manufacturer/model we must be directed to the fixed config step
    assert result["type"] == FlowResultType.CREATE_ENTRY

    await async_setup_entry(hass, result["result"])

    hass.states.async_set(switch_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.70"

    hass.states.async_set(switch_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.30"


async def test_hue_smart_plug_is_discovered(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    mock_entity_with_model_information(
        entity_id="switch.smartplug",
        manufacturer="signify",
        model="LOM002",
        platform="hue",
        unique_id="1234",
    )
    await run_powercalc_setup(hass, {})

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}


async def start_discovery_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    entity_id: str,
    manufacturer: str,
    model: str,
) -> FlowResult:
    hass.config.config_dir = get_test_config_dir()

    mock_entity_with_model_information(
        entity_id=entity_id,
        manufacturer=manufacturer,
        model=model,
    )

    await run_powercalc_setup(hass, {})

    # Retrieve the discovery flow
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    flow = flows[0]

    assert flow["step_id"] == Step.LIBRARY
    return await confirm_auto_discovered_model(hass, flow)
