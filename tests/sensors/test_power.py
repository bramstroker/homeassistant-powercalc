from datetime import timedelta
from decimal import Decimal
import logging
import uuid

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
)
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.components.vacuum import (
    ATTR_BATTERY_LEVEL,
    VacuumActivity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ATTRIBUTE,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_CLOSED,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import EVENT_HOMEASSISTANT_START, CoreState, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.template import Template
from homeassistant.util import dt
import pytest
from pytest_homeassistant_custom_component.common import (
    RegistryEntryWithDefaults,
    async_fire_time_changed,
    mock_registry,
)

from custom_components.powercalc import CONF_IGNORE_UNAVAILABLE_STATE, CONF_POWER_UPDATE_INTERVAL
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_AVAILABILITY_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CALIBRATE,
    CONF_CREATE_GROUP,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DELAY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SENSOR_TYPE,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_UNAVAILABLE_POWER,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_SWITCH_SUB_PROFILE,
    CalculationStrategy,
    SensorType,
)
from tests.common import (
    assert_entity_state,
    create_input_boolean,
    create_mock_config_entry,
    get_simple_fixed_config,
    get_test_profile_dir,
    run_powercalc_setup,
    set_states,
)
from tests.conftest import MockEntityWithModel


@pytest.mark.parametrize(
    ("case", "expected_type", "expected_value"),
    [
        ("template", Template, None),
        ("template_string", Template, None),
        (None, Decimal, Decimal(0)),
        (Decimal("1.5"), Decimal, Decimal("1.5")),
        (2.5, Decimal, Decimal("2.5")),
        (3, Decimal, Decimal(3)),
    ],
)
def test_resolve_standby_power_value(
    hass: HomeAssistant,
    case: Template | Decimal | str | float | None,
    expected_type: type[Template] | type[Decimal],
    expected_value: Decimal | None,
) -> None:
    from custom_components.powercalc.sensors.power import _resolve_standby_power_value

    value: Template | Decimal | str | float | int | None
    if case == "template":
        value = Template("{{ 10 }}", hass)
    elif case == "template_string":
        value = "{{ 20 }}"
    else:
        value = case

    resolved = _resolve_standby_power_value(hass, value)

    assert isinstance(resolved, expected_type)
    if isinstance(resolved, Template):
        if isinstance(value, Template):
            assert resolved is value
        else:
            assert resolved.template == value
    else:
        assert resolved == expected_value


async def test_use_real_power_sensor_in_group(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    mock_registry(
        hass,
        {
            "sensor.existing_power": RegistryEntryWithDefaults(
                entity_id="sensor.existing_power",
                unique_id="1234",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                },
            ],
        },
    )

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
        "sensor.test_power",
    }


async def test_rounding_precision(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test", 50),
        {CONF_POWER_SENSOR_PRECISION: 4},
    )

    power_entry = entity_registry.async_get("sensor.test_power")
    assert power_entry
    assert power_entry.options == {"sensor": {"suggested_display_precision": 4}}

    assert_entity_state(hass, "sensor.test_power", "0.0000")

    await set_states(hass, [("input_boolean.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "50.0000")


async def test_initial_state_is_calculated_after_startup(hass: HomeAssistant) -> None:
    """
    The initial state of the power sensor should be calculated after HA startup completes.
    When we do it already during powercalc setup some entities referred in template could be unknown yet
    """
    hass.state = CoreState.not_running

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Henkie",
            CONF_FIXED: {CONF_POWER: "{{states('input_number.test')}}"},
        },
    )

    await set_states(hass, [("input_number.test", 30)])
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)

    assert_entity_state(hass, "sensor.henkie_power", "30.00")


async def test_standby_power(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 0.5,
            CONF_FIXED: {CONF_POWER: 15},
        },
    )

    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "0.50")

    await set_states(hass, [("input_boolean.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "15.00")


async def test_multiply_factor(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 0.2,
            CONF_MULTIPLY_FACTOR_STANDBY: True,
            CONF_MULTIPLY_FACTOR: 3,
            CONF_FIXED: {CONF_POWER: 5},
        },
    )

    assert_entity_state(hass, "sensor.test_power", "0.60")

    await set_states(hass, [("input_boolean.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "15.00")


async def test_error_when_no_strategy_has_been_configured(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "input_boolean.test"},
    )

    assert "Skipping sensor setup" in caplog.text


async def test_strategy_enabled_condition(hass: HomeAssistant) -> None:
    """
    Test calculation_enabled_condition is working correctly.
    This is used for example on robot vacuum cleaners.
    This test simulates a vacuum cleaner going through following stages:
     - cleaning
     - returning
     - docked
    When the state is docked the calculation is activated and linear calibration is used to map the consumption
    while charging
    """
    vacuum_entity_id = "vacuum.my_robot_cleaner"
    power_entity_id = "sensor.my_robot_cleaner_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: vacuum_entity_id,
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
            CONF_LINEAR: {
                CONF_ATTRIBUTE: "battery_level",
                CONF_CALIBRATE: [
                    "1 -> 20",
                    "79 -> 20",
                    "80 -> 15",
                    "99 -> 8",
                    "100 -> 1.5",
                ],
            },
        },
    )

    assert hass.states.get(power_entity_id)

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.CLEANING, {ATTR_BATTERY_LEVEL: 40})])
    assert_entity_state(hass, power_entity_id, "0.00")

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.RETURNING, {ATTR_BATTERY_LEVEL: 40})])
    assert_entity_state(hass, power_entity_id, "0.00")

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.DOCKED, {ATTR_BATTERY_LEVEL: 20})])
    assert_entity_state(hass, power_entity_id, "20.00")

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.DOCKED, {ATTR_BATTERY_LEVEL: 60})])
    assert_entity_state(hass, power_entity_id, "20.00")

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.DOCKED, {ATTR_BATTERY_LEVEL: 80})])
    assert_entity_state(hass, power_entity_id, "15.00")

    await set_states(hass, [(vacuum_entity_id, VacuumActivity.DOCKED, {ATTR_BATTERY_LEVEL: 100})])
    assert_entity_state(hass, power_entity_id, "1.50")


async def test_strategy_enabled_condition_template_tracking(
    hass: HomeAssistant,
) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.my_entity",
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('sensor.other_entity', 'foo') }}",
            CONF_FIXED: {
                CONF_POWER: 5,
            },
        },
    )

    await set_states(hass, [("sensor.my_entity", STATE_ON)])
    assert_entity_state(hass, "sensor.my_entity_power", "0.00")

    await set_states(hass, [("sensor.other_entity", "foo")])
    assert_entity_state(hass, "sensor.my_entity_power", "5.00")

    await set_states(hass, [("sensor.other_entity", "bar")])
    assert_entity_state(hass, "sensor.my_entity_power", "0.00")


async def test_template_entity_tracking(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_number.test",
            CONF_FIXED: {CONF_POWER: "{{ states('input_number.test') }}"},
        },
    )

    await set_states(hass, [("input_number.test", 0)])
    assert_entity_state(hass, "sensor.test_power", "0.00")

    await set_states(hass, [("input_number.test", 15)])
    assert_entity_state(hass, "sensor.test_power", "15.00")


async def test_template_entity_not_double_tracked(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """When the source entity is also used in the template, it should not be double tracked"""
    caplog.set_level(logging.ERROR)

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Dynamic input number",
            CONF_ENTITY_ID: "input_number.my_entity",
            CONF_FIXED: {
                CONF_POWER: "{{ states('input_number.my_entity') | float(0) }}",
            },
        },
    )

    assert hass.states.get("sensor.dynamic_input_number_power")
    assert len(caplog.records) == 0


async def test_unknown_source_entity_state(hass: HomeAssistant) -> None:
    """Power sensor should be unavailable when source entity state is unknown"""
    await create_input_boolean(hass)
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {CONF_POWER: 20},
        },
    )
    await set_states(hass, [("input_boolean.test", STATE_UNKNOWN)])
    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)


async def test_error_when_model_not_supported(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MANUFACTURER: "Foo",
            CONF_MODEL: "Bar",
        },
    )

    assert not hass.states.get("sensor.test_power")

    assert "Skipping sensor setup" in caplog.text


async def test_sleep_power(hass: HomeAssistant) -> None:
    """Test sleep power for devices having a sleep mode"""
    entity_id = "media_player.test"
    power_entity_id = "sensor.test_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_STANDBY_POWER: 20,
            CONF_SLEEP_POWER: {CONF_POWER: 5, CONF_DELAY: 10},
            CONF_FIXED: {CONF_POWER: 100},
        },
    )

    await set_states(hass, [(entity_id, STATE_OFF)])
    assert_entity_state(hass, power_entity_id, "20.00")

    # After 10 seconds the device goes into sleep mode, check the sleep power is set on the power sensor
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=10))

    assert_entity_state(hass, power_entity_id, "5.00")

    await set_states(hass, [(entity_id, STATE_ON)])
    assert_entity_state(hass, power_entity_id, "100.00")

    await set_states(hass, [(entity_id, STATE_OFF)])
    assert_entity_state(hass, power_entity_id, "20.00")

    # Check that the sleepmode timer is reset correctly when the device goes to a non OFF state again
    await set_states(hass, [(entity_id, STATE_ON)])
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=20))

    assert_entity_state(hass, power_entity_id, "100.00")


async def test_unavailable_power(hass: HomeAssistant) -> None:
    """Test specifying an alternative power value if the source entity is unavailable"""
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 20,
            CONF_UNAVAILABLE_POWER: 0,
            CONF_FIXED: {CONF_POWER: 100},
        },
    )

    await set_states(hass, [("input_boolean.test", STATE_UNAVAILABLE)])
    assert_entity_state(hass, "sensor.test_power", "0.00")


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_DISABLE_EXTENDED_ATTRIBUTES: True},
    )

    power_state = hass.states.get("sensor.test_power")
    assert ATTR_SOURCE_ENTITY not in power_state.attributes
    assert ATTR_SOURCE_DOMAIN not in power_state.attributes


async def test_manually_configured_sensor_overrides_profile(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    Make sure that config settings done by user are not overridden by power profile
    """
    entity_id = "light.test"

    mock_entity_with_model_information(entity_id, "sonoff", "ZBMINI")

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: entity_id,
            CONF_NAME: "Test 123",
            CONF_UNIQUE_ID: "1234353",
            CONF_STANDBY_POWER: 0,
            CONF_FIXED: {CONF_POWER: 6},
        },
    )

    await set_states(hass, [("light.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_123_power", "6.00")

    await set_states(hass, [("light.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_123_power", "0.00")


async def test_standby_power_template(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_STANDBY_POWER: "{{ states('input_number.test') }}",
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    await set_states(hass, [("input_number.test", 20)])
    assert_entity_state(hass, "sensor.test_power", "20.00")

    await set_states(hass, [("input_number.test", 60)])
    assert_entity_state(hass, "sensor.test_power", "60.00")


async def test_power_state_unavailable_when_source_entity_has_no_state(
    hass: HomeAssistant,
) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 40},
        },
    )
    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)


async def test_multiply_factor_standby(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
            CONF_STANDBY_POWER: 2,
            CONF_MULTIPLY_FACTOR: 4,
            CONF_MULTIPLY_FACTOR_STANDBY: True,
        },
    )
    await set_states(hass, [("switch.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "8.00")

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "40.00")


async def test_multiply_factor_standby_power_on(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MANUFACTURER: "IKEA",
            CONF_MODEL: "IKEA Control outlet",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("smart_switch"),
            CONF_MULTIPLY_FACTOR: 2,
            CONF_MULTIPLY_FACTOR_STANDBY: True,
        },
    )

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "1.64")


async def test_multiply_factor_sleep_power(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
            CONF_SLEEP_POWER: {
                CONF_POWER: 2,
                CONF_DELAY: 20,
            },
            CONF_MULTIPLY_FACTOR: 2,
            CONF_MULTIPLY_FACTOR_STANDBY: True,
        },
    )

    await set_states(hass, [("switch.test", STATE_OFF)])
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=25))

    assert_entity_state(hass, "sensor.test_power", "4.00")


async def test_unload_entry_cancels_pending_sleep_power_timer(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: str(uuid.uuid4()),
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
            CONF_SLEEP_POWER: {
                CONF_POWER: 2,
                CONF_DELAY: 20,
            },
        },
    )

    await set_states(hass, [("switch.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "0.00")

    await hass.config_entries.async_unload(entry.entry_id)

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=25))

    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)


async def test_standby_power_invalid_template(hass: HomeAssistant) -> None:
    """Test when the template does not return a decimal it does not break the powercalc sensor"""

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
            CONF_STANDBY_POWER: "{{ states('sensor.foo') }}",
        },
    )

    await set_states(hass, [("switch.test", STATE_OFF), ("sensor.foo", "bla")])
    assert_entity_state(hass, "sensor.test_power", "0.00")

    await set_states(hass, [("sensor.foo", "20")])
    assert_entity_state(hass, "sensor.test_power", "20.00")


async def test_entity_category(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    """Test setting an entity_category on the power sensor"""

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
            CONF_UNIQUE_ID: "123",
            CONF_POWER_SENSOR_CATEGORY: EntityCategory.DIAGNOSTIC,
        },
    )

    power_entry = entity_registry.async_get("sensor.test_power")
    assert power_entry
    assert power_entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_sub_profile_default_select(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile_default",
        },
    )

    await set_states(hass, [("switch.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_device_power", "0.80")


async def test_switch_sub_profile_service(hass: HomeAssistant) -> None:
    unique_id = str(uuid.uuid4())
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: "camera.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile_camera/default",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("sub_profile_camera"),
        },
        unique_id,
    )

    await set_states(hass, [("camera.test", STATE_IDLE)])
    await run_powercalc_setup(hass)

    assert_entity_state(hass, "sensor.test_power", "1.32")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SWITCH_SUB_PROFILE,
        {
            ATTR_ENTITY_ID: "sensor.test_power",
            "profile": "night_vision",
        },
        blocking=True,
    )

    await hass.async_block_till_done()
    assert_entity_state(hass, "sensor.test_power", "2.35")

    config_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert config_entry.data.get(CONF_MODEL) == "sub_profile_camera/night_vision"

    # Trigger again for coverage, this should not change the state / raise an exception
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SWITCH_SUB_PROFILE,
        {
            ATTR_ENTITY_ID: "sensor.test_power",
            "profile": "night_vision",
        },
        blocking=True,
    )


async def test_switch_sub_profile_raises_exception_when_profile_has_no_sub_profiles(
    hass: HomeAssistant,
) -> None:
    unique_id = str(uuid.uuid4())
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "fixed/a",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("fixed"),
        },
        unique_id,
    )

    await set_states(hass, [("light.test", STATE_ON)])
    await run_powercalc_setup(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SWITCH_SUB_PROFILE,
            {
                ATTR_ENTITY_ID: "sensor.test_power",
                "profile": "b",
            },
            blocking=True,
        )


async def test_switch_sub_profile_raises_exception_on_invalid_sub_profile(
    hass: HomeAssistant,
) -> None:
    unique_id = str(uuid.uuid4())
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile/a",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("sub_profile2"),
        },
        unique_id,
    )

    await set_states(
        hass,
        [
            (
                "light.test",
                STATE_ON,
                {
                    ATTR_BRIGHTNESS: 20,
                    ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
                    ATTR_COLOR_TEMP_KELVIN: 50000,
                },
            ),
        ],
    )
    await run_powercalc_setup(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SWITCH_SUB_PROFILE,
            {
                ATTR_ENTITY_ID: "sensor.test_power",
                "profile": "c",
            },
            blocking=True,
        )


async def test_availability_entity(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_NAME: "Test",
            CONF_AVAILABILITY_ENTITY: "sensor.availability",
            CONF_FIXED: {CONF_POWER: 10},
        },
    )

    await set_states(hass, [("sensor.availability", STATE_UNAVAILABLE)])
    assert_entity_state(hass, "sensor.test_power", STATE_UNAVAILABLE)

    await set_states(hass, [("sensor.availability", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "10.00")


async def test_dummy_source_ignores_availability_entity_state_for_power_calculation(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_AVAILABILITY_ENTITY: "binary_sensor.availability",
            CONF_FIXED: {CONF_POWER: 10},
        },
    )

    await set_states(hass, [("binary_sensor.availability", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_power", "10.00")

    await set_states(hass, [("binary_sensor.availability", STATE_ON)])
    assert_entity_state(hass, "sensor.test_power", "10.00")


async def test_cover_entity_standby_power(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "cover.test",
            CONF_STANDBY_POWER: 1.5,
            CONF_FIXED: {CONF_POWER: 10},
        },
    )

    await set_states(hass, [("cover.test", STATE_CLOSED)])
    assert_entity_state(hass, "sensor.test_power", "1.50")

    await set_states(hass, [("cover.test", STATE_OPEN)])
    assert_entity_state(hass, "sensor.test_power", "1.50")

    await set_states(hass, [("cover.test", STATE_OPENING)])
    assert_entity_state(hass, "sensor.test_power", "10.00")


async def test_force_update_interval(hass: HomeAssistant) -> None:
    """Test that the power sensor state is forcefully updated at the configured interval"""
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_FIXED: {CONF_POWER: 10},
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {
            CONF_POWER_UPDATE_INTERVAL: 20,
        },
    )

    time = dt.utcnow()
    prev = hass.states.get("sensor.test_power")
    assert prev

    for i in range(1, 4):
        async_fire_time_changed(hass, time + timedelta(seconds=20 * i))

        cur = hass.states.get("sensor.test_power")
        assert cur
        assert cur.state == prev.state
        assert cur.last_updated > prev.last_updated
        prev = cur
