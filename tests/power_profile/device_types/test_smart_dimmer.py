from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_SUPPORTED_COLOR_MODES, ColorMode
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.issue_registry import IssueRegistry
from homeassistant.helpers.selector import SelectSelector
import pytest

from custom_components.powercalc import CONF_IGNORE_UNAVAILABLE_STATE, async_setup_entry
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_GAMMA_CURVE,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER_CURVE,
    CONF_SUB_PROFILE,
    DOMAIN,
    SERVICE_SWITCH_SUB_PROFILE,
    CalculationStrategy,
)
from custom_components.powercalc.flow_helper.flows.library import CONF_CONFIRM_AUTODISCOVERED_MODEL
from custom_components.powercalc.flow_helper.schema import MANUAL_POWER_OPTION
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    get_test_profile_dir,
    mock_device_with_entities,
    run_powercalc_setup,
    set_states,
)
from tests.config_flow.common import confirm_auto_discovered_model, handle_options_flow_update, initialize_options_flow

TRADFRI_DRIVER = "ICPSHC24-10EU-IL-1"
NORRFLY_SUB_PROFILE = "1x_norrfly_5w"
LIGHT_AT_FULL_BRIGHTNESS = {
    ATTR_BRIGHTNESS: 255,
    ATTR_COLOR_MODE: ColorMode.BRIGHTNESS,
    ATTR_SUPPORTED_COLOR_MODES: [ColorMode.BRIGHTNESS],
}


@pytest.mark.parametrize(
    "choice, linear_input, expected_power",
    [
        (NORRFLY_SUB_PROFILE, None, "5.90"),
        (MANUAL_POWER_OPTION, {CONF_MIN_POWER: 1, CONF_MAX_POWER: 4}, "4.10"),
        (MANUAL_POWER_OPTION, {}, "0.10"),
    ],
)
async def test_tradfri_driver_discovery(
    hass: HomeAssistant,
    issue_registry: IssueRegistry,
    choice: str,
    linear_input: dict[str, int] | None,
    expected_power: str,
) -> None:
    mock_device_with_entities(hass, "light.test", "ikea", TRADFRI_DRIVER)
    await set_states(hass, [("light.test", STATE_ON, LIGHT_AT_FULL_BRIGHTNESS)])
    await run_powercalc_setup(hass)

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )
    assert result["step_id"] == Step.SUB_PROFILE
    schema = result["data_schema"]
    assert schema is not None
    picker = schema.schema[CONF_SUB_PROFILE]
    assert isinstance(picker, SelectSelector)
    assert [option["value"] for option in picker.config["options"]] == [NORRFLY_SUB_PROFILE, MANUAL_POWER_OPTION]

    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_SUB_PROFILE: choice})
    if linear_input is not None:
        assert result["step_id"] == Step.LINEAR
        placeholders = result["description_placeholders"]
        assert placeholders is not None
        assert "Leave all fields blank" in placeholders["manual_dimmer_power_remarks"]
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], linear_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    if linear_input is None:
        assert entry.data[CONF_MODEL] == f"{TRADFRI_DRIVER}/{NORRFLY_SUB_PROFILE}"
        assert entry.data[CONF_MODE] == CalculationStrategy.LUT
    else:
        assert entry.data[CONF_MODEL] == TRADFRI_DRIVER
        assert entry.data[CONF_MODE] == CalculationStrategy.LINEAR
        assert entry.data[CONF_LINEAR] == linear_input

    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert_entity_state(hass, "sensor.test_power", expected_power)
    assert not issue_registry.async_get_issue(DOMAIN, f"sub_profile_{entry.entry_id}")

    if linear_input == {}:
        await set_states(hass, [("light.test", STATE_ON)])
        assert_entity_state(hass, "sensor.test_power", "0.10")

    await set_states(hass, [("light.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "0.10")


async def test_tradfri_driver_change_power_method(hass: HomeAssistant) -> None:
    await set_states(hass, [("light.test", STATE_ON, LIGHT_AT_FULL_BRIGHTNESS)])
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "ikea",
            CONF_MODEL: f"{TRADFRI_DRIVER}/{NORRFLY_SUB_PROFILE}",
        },
    )
    assert_entity_state(hass, "sensor.test_power", "5.90")

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)
    configure = hass.config_entries.options.async_configure
    flow_id = result["flow_id"]
    await configure(flow_id, {})
    await configure(flow_id, {CONF_MANUFACTURER: "ikea"})
    result = await configure(flow_id, {CONF_MODEL: TRADFRI_DRIVER})
    assert result["step_id"] == Step.SUB_PROFILE

    result = await configure(flow_id, {CONF_SUB_PROFILE: MANUAL_POWER_OPTION})
    assert result["step_id"] == Step.LINEAR
    result = await configure(flow_id, {CONF_MIN_POWER: 1})
    assert result["errors"] == {"base": "linear_mandatory"}
    assert entry.data[CONF_MODEL] == f"{TRADFRI_DRIVER}/{NORRFLY_SUB_PROFILE}"

    result = await configure(flow_id, {CONF_MIN_POWER: 1, CONF_MAX_POWER: 4})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_MODEL] == TRADFRI_DRIVER
    assert entry.data[CONF_MODE] == CalculationStrategy.LINEAR
    assert_entity_state(hass, "sensor.test_power", "4.10")

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SWITCH_SUB_PROFILE,
            {CONF_ENTITY_ID: "sensor.test_power", "profile": NORRFLY_SUB_PROFILE},
            blocking=True,
        )
    assert entry.data[CONF_MODEL] == TRADFRI_DRIVER

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)
    flow_id = result["flow_id"]
    await configure(flow_id, {})
    await configure(flow_id, {CONF_MANUFACTURER: "ikea"})
    result = await configure(flow_id, {CONF_MODEL: TRADFRI_DRIVER})
    assert result["step_id"] == Step.SUB_PROFILE
    schema = result["data_schema"]
    assert schema is not None
    choice = next(iter(schema.schema))
    assert choice.default() == MANUAL_POWER_OPTION

    result = await configure(flow_id, {CONF_SUB_PROFILE: NORRFLY_SUB_PROFILE})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_MODEL] == f"{TRADFRI_DRIVER}/{NORRFLY_SUB_PROFILE}"
    assert entry.data[CONF_MODE] == CalculationStrategy.LUT
    assert CONF_LINEAR not in entry.data
    assert_entity_state(hass, "sensor.test_power", "5.90")


async def test_tradfri_driver_change_library_model(hass: HomeAssistant) -> None:
    await set_states(hass, [("light.test", STATE_OFF)])
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "ikea",
            CONF_MODEL: TRADFRI_DRIVER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MAX_POWER: 4},
        },
    )
    assert_entity_state(hass, "sensor.test_power", "0.10")

    result = await initialize_options_flow(hass, entry, Step.LIBRARY_OPTIONS)
    configure = hass.config_entries.options.async_configure
    flow_id = result["flow_id"]
    await configure(flow_id, {})
    await configure(flow_id, {CONF_MANUFACTURER: "ikea"})
    result = await configure(flow_id, {CONF_MODEL: "LED1739R5"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_MODEL] == "LED1739R5"
    assert CONF_MODE not in entry.data
    assert CONF_LINEAR not in entry.data
    assert_entity_state(hass, "sensor.test_power", "0.26")


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
