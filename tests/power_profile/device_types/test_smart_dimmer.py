from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.powercalc import CONF_IGNORE_UNAVAILABLE_STATE, async_setup_entry
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_GAMMA_CURVE,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER_CURVE,
    DOMAIN,
)
from tests.common import (
    assert_entity_state,
    get_test_profile_dir,
    mock_device_with_entities,
    run_powercalc_setup,
    set_states,
)
from tests.config_flow.common import confirm_auto_discovered_model, handle_options_flow_update


async def test_smart_dimmer_power_input_yaml(
    hass: HomeAssistant,
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

    await set_states(hass, [(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 255})])
    assert_entity_state(hass, power_sensor_id, "50.50")

    await set_states(hass, [(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 10})])
    assert_entity_state(hass, power_sensor_id, "3.90")

    await set_states(hass, [(switch_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "0.30")


async def test_smart_dimmer_power_input_yaml_omit_linear_config(
    hass: HomeAssistant,
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

    await set_states(hass, [(switch_id, STATE_ON, {ATTR_BRIGHTNESS: 255})])
    assert_entity_state(hass, power_sensor_id, "0.50")

    await set_states(hass, [(switch_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "0.30")


async def test_smart_dimmer_profile_gamma_combined_with_user_power_input(
    hass: HomeAssistant,
) -> None:
    """Test profile gamma is combined with user supplied min and max power."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_gamma"),
            CONF_LINEAR: {CONF_MIN_POWER: 1.5, CONF_MAX_POWER: 50},
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "14.22")


async def test_smart_dimmer_user_gamma_overrides_profile_gamma(
    hass: HomeAssistant,
) -> None:
    """Test an explicitly supplied gamma overrides the profile gamma."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_gamma"),
            CONF_LINEAR: {
                CONF_MIN_POWER: 1.5,
                CONF_MAX_POWER: 50,
                CONF_GAMMA_CURVE: 1,
            },
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "26.35")


async def test_smart_dimmer_user_calibration_ignores_profile_gamma(
    hass: HomeAssistant,
) -> None:
    """Test an existing user calibration is not modified by profile gamma."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_gamma"),
            CONF_LINEAR: {CONF_CALIBRATE: ["0 -> 1.5", "255 -> 50"]},
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "26.35")


async def test_smart_dimmer_profile_gamma_without_user_power_input(
    hass: HomeAssistant,
) -> None:
    """Test profile gamma keeps the self-usage-only YAML configuration valid."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_gamma"),
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})])
    assert_entity_state(hass, power_sensor_id, "0.50")


async def test_smart_dimmer_profile_power_curve_combined_with_user_power_input(
    hass: HomeAssistant,
) -> None:
    """Test a profile power curve is scaled with user supplied min and max power."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_power_curve"),
            CONF_LINEAR: {CONF_MIN_POWER: 2, CONF_MAX_POWER: 12},
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "4.53")


async def test_smart_dimmer_user_gamma_overrides_profile_power_curve(
    hass: HomeAssistant,
) -> None:
    """Test an explicitly supplied gamma overrides the profile power curve."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_power_curve"),
            CONF_LINEAR: {
                CONF_MIN_POWER: 2,
                CONF_MAX_POWER: 12,
                CONF_GAMMA_CURVE: 1,
            },
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "7.52")


async def test_smart_dimmer_user_calibration_ignores_profile_power_curve(
    hass: HomeAssistant,
) -> None:
    """Test user calibration is not modified by a profile power curve."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_power_curve"),
            CONF_LINEAR: {CONF_CALIBRATE: ["0 -> 2", "255 -> 12"]},
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "7.52")


async def test_smart_dimmer_user_power_curve_overrides_profile_gamma(
    hass: HomeAssistant,
) -> None:
    """Test an explicitly supplied power curve overrides the profile gamma."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: light_entity_id,
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_dimmer_gamma"),
            CONF_LINEAR: {
                CONF_MIN_POWER: 2,
                CONF_MAX_POWER: 12,
                CONF_POWER_CURVE: ["0 -> 0", "0.5 -> 0.2", "1 -> 1"],
            },
        },
    )

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "4.53")


async def test_smart_dimmer_power_input_gui_config_flow(
    hass: HomeAssistant,
) -> None:
    """
    Test a smart dimmer can be setup with GUI and a fixed power value for the light configured by the user
    The values for standby power on and off should be taken from the power profile library.
    The linear power value from the user should be added to the total power consumption. standby_power_on + power
    """
    light_entity_id = "light.test"
    manufacturer = "test"
    model = "smart_dimmer"

    mock_device_with_entities(
        hass,
        entity_ids=light_entity_id,
        manufacturer=manufacturer,
        model=model,
    )

    power_sensor_id = "sensor.test_power"

    await run_powercalc_setup(hass)

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
    await hass.async_block_till_done()

    config_entry = result["result"]

    # Toggle the switch to different states and check for correct power values
    assert_entity_state(hass, power_sensor_id, STATE_UNAVAILABLE)

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})])
    assert_entity_state(hass, power_sensor_id, "50.50")

    await set_states(hass, [(light_entity_id, STATE_OFF)])
    assert_entity_state(hass, power_sensor_id, "0.30")

    # Change the power value via the options
    await handle_options_flow_update(hass, config_entry, Step.LINEAR, {CONF_MIN_POWER: 4, CONF_MAX_POWER: 40})

    # Set the switch on again and see if it has the updated power value
    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255})])
    assert_entity_state(hass, power_sensor_id, "40.50")


async def test_smart_dimmer_profile_gamma_gui_config_flow(
    hass: HomeAssistant,
) -> None:
    """Test a partial profile linear config still requests the lamp power values."""
    light_entity_id = "light.test"
    power_sensor_id = "sensor.test_power"

    mock_device_with_entities(
        hass,
        entity_ids=light_entity_id,
        manufacturer="test",
        model="smart_dimmer_gamma",
    )

    await run_powercalc_setup(hass)

    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
    result = await confirm_auto_discovered_model(hass, flow)

    assert result["step_id"] == Step.LINEAR
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_MIN_POWER: 1.5, CONF_MAX_POWER: 50},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LINEAR] == {CONF_MIN_POWER: 1.5, CONF_MAX_POWER: 50}

    await async_setup_entry(hass, result["result"])
    await hass.async_block_till_done()

    await set_states(hass, [(light_entity_id, STATE_ON, {ATTR_BRIGHTNESS: 128})])
    assert_entity_state(hass, power_sensor_id, "14.22")
