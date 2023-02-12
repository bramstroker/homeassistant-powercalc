from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

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


async def test_smart_switch(hass: HomeAssistant):
    """
    Test that smart plug can be setup from profile library
    """
    switch_id = "switch.oven"
    manufacturer = "Shelly"
    model = "Shelly Plug S"

    mock_registry(
        hass,
        {
            switch_id: RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id="shelly-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "shelly-device": DeviceEntry(
                id="shelly-device-id", manufacturer=manufacturer, model=model
            )
        },
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


async def test_smart_switch_power_input_yaml(hass: HomeAssistant):
    """
    Test a smart switch can be setup with YAML and a fixed power value for the appliance configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The fixed power value from the user should be added to the total power consumption. standby_power_on + power
    """
    switch_id = "switch.heater"
    manufacturer = "IKEA"
    model = "Smart Control Outlet"

    mock_registry(
        hass,
        {
            switch_id: RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id="ikea-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "ikea-device-id": DeviceEntry(
                id="ikea-device-id", manufacturer=manufacturer, model=model
            )
        },
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


async def test_smart_switch_power_input_gui_config_flow(hass: HomeAssistant):
    """
    Test a smart switch can be setup with GUI and a fixed power value for the appliance configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The fixed power value from the user should be added to the total power consumption. standby_power_on + power
    """
    switch_id = "switch.heater"
    manufacturer = "IKEA"
    model = "TRADFRI control outlet"

    mock_registry(
        hass,
        {
            switch_id: RegistryEntry(
                entity_id=switch_id,
                unique_id="1234",
                platform="switch",
                device_id="ikea-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "ikea-device-id": DeviceEntry(
                id="ikea-device-id", manufacturer=manufacturer, model=model
            )
        },
    )

    power_sensor_id = "sensor.heater_device_power"

    await run_powercalc_setup(hass, {})

    # Retrieve the discovery flow
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    flow = flows[0]

    assert flow["step_id"] == "library"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_CONFIRM_AUTODISCOVERED_MODEL: True}
    )

    # After confirming the manufacturer/model we must be directed to the fixed config step
    assert result["step_id"] == "fixed"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_POWER: 50}
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


async def test_switch_as_x_added_through_discovery(
    hass: HomeAssistant, mock_flow_init
) -> None:
    """
    Test that smart plug can be setup from profile library
    """
    entity_id = "light.foo"
    manufacturer = "Signify"
    model = "LOM007"
    device_id = "mydevice"

    mock_registry(
        hass,
        {
            entity_id: RegistryEntry(
                entity_id=entity_id,
                unique_id="1234",
                platform="switch_as_x",
                device_id=device_id,
            ),
        },
    )
    mock_device_registry(
        hass,
        {device_id: DeviceEntry(id=device_id, manufacturer=manufacturer, model=model)},
    )

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    # Check that two discovery flows have been initialized
    # LightA and LightB should be discovered, LightC not
    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    assert mock_calls[0][2]["data"][CONF_ENTITY_ID] == entity_id
