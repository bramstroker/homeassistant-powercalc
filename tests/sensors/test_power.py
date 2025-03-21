import logging
import uuid
from datetime import timedelta

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
)
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.components.vacuum import (
    ATTR_BATTERY_LEVEL,
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_RETURNING,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ATTRIBUTE,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import EVENT_HOMEASSISTANT_START, CoreState, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    MockEntity,
    MockEntityPlatform,
    async_fire_time_changed,
)

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
    create_input_number,
    get_simple_fixed_config,
    get_test_config_dir,
    get_test_profile_dir,
    run_powercalc_setup,
    setup_config_entry,
)
from tests.conftest import MockEntityWithModel


async def test_use_real_power_sensor_in_group(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    platform = MockEntityPlatform(hass)
    entity = MockEntity(
        name="existing_power",
        unique_id="1234",
        device_class=SensorDeviceClass.POWER,
    )
    await platform.async_add_entities([entity])

    await hass.async_block_till_done()

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

    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
        "sensor.test_power",
    }


async def test_rounding_precision(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test", 50),
        {CONF_POWER_SENSOR_PRECISION: 4},
    )

    state = hass.states.get("sensor.test_power")
    assert state.state == "0.0000"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "50.0000"


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

    await create_input_number(hass, "test", 30)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henkie_power").state == "30.00"


async def test_standby_power(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_STANDBY_POWER: 0.5,
            CONF_FIXED: {CONF_POWER: 15},
        },
    )

    hass.states.async_set("input_boolean.test", STATE_OFF)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "0.50"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "15.00"


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

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "0.60"

    hass.states.async_set("input_boolean.test", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.test_power")
    assert power_state.state == "15.00"


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

    hass.states.async_set(vacuum_entity_id, STATE_CLEANING, {ATTR_BATTERY_LEVEL: 40})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "0.00"

    hass.states.async_set(vacuum_entity_id, STATE_RETURNING, {ATTR_BATTERY_LEVEL: 40})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "0.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 20})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 60})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 80})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "15.00"

    hass.states.async_set(vacuum_entity_id, STATE_DOCKED, {ATTR_BATTERY_LEVEL: 100})
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "1.50"


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

    hass.states.async_set("sensor.my_entity", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.my_entity_power").state == "0.00"

    hass.states.async_set("sensor.other_entity", "foo")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.my_entity_power").state == "5.00"

    hass.states.async_set("sensor.other_entity", "bar")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.my_entity_power").state == "0.00"


async def test_template_entity_tracking(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 0)
    await create_input_boolean(hass)

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_number.test",
            CONF_FIXED: {CONF_POWER: "{{ states('input_number.test') }}"},
        },
    )

    hass.states.async_set("input_number.test", 0)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"

    hass.states.async_set("input_number.test", 15)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "15.00"


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
    hass.states.async_set("input_boolean.test", STATE_UNKNOWN)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE


async def test_error_when_model_not_supported(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    await create_input_boolean(hass)
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

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    # After 10 seconds the device goes into sleep mode, check the sleep power is set on the power sensor
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "5.00"

    hass.states.async_set(entity_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "100.00"

    hass.states.async_set(entity_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "20.00"

    # Check that the sleepmode timer is reset correctly when the device goes to a non OFF state again
    hass.states.async_set(entity_id, STATE_ON)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=20))
    await hass.async_block_till_done()

    assert hass.states.get(power_entity_id).state == "100.00"


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

    hass.states.async_set("input_boolean.test", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

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
    Make sure that config settings done by user are not overriden by power profile
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

    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    assert_entity_state(hass, "sensor.test_123_power", "6.00")

    hass.states.async_set("light.test", STATE_OFF)
    await hass.async_block_till_done()

    assert_entity_state(hass, "sensor.test_123_power", "0.00")


async def test_standby_power_template(hass: HomeAssistant) -> None:
    await create_input_number(hass, "test", 0)
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

    hass.states.async_set("input_number.test", 20)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.00"

    hass.states.async_set("input_number.test", 60)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "60.00"


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
    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE


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
    hass.states.async_set("switch.test", STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "8.00"

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "40.00"


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

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1.64"


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

    hass.states.async_set("switch.test", STATE_OFF)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=25))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "4.00"


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

    hass.states.async_set("switch.test", STATE_OFF)
    hass.states.async_set("sensor.foo", "bla")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"

    hass.states.async_set("sensor.foo", "20")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.00"


async def test_entity_category(hass: HomeAssistant) -> None:
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

    entity_registry = er.async_get(hass)
    power_entry = entity_registry.async_get("sensor.test_power")
    assert power_entry
    assert power_entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_sub_profile_default_select(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile_default",
        },
    )

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_device_power").state == "0.80"


async def test_switch_sub_profile_service(hass: HomeAssistant) -> None:
    unique_id = str(uuid.uuid4())
    entry = await setup_config_entry(
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

    hass.states.async_set("camera.test", STATE_IDLE)

    await run_powercalc_setup(hass, {})

    power_state = hass.states.get("sensor.test_power")
    assert power_state
    assert power_state.state == "1.32"

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

    power_state = hass.states.get("sensor.test_power")
    assert power_state
    assert power_state.state == "2.35"

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
    await setup_config_entry(
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

    hass.states.async_set("light.test", STATE_ON)

    await run_powercalc_setup(hass, {})

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
    await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile/a",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("sub_profile"),
        },
        unique_id,
    )

    hass.states.async_set(
        "light.test",
        STATE_ON,
        {
            ATTR_BRIGHTNESS: 20,
            ATTR_COLOR_MODE: ColorMode.COLOR_TEMP,
            ATTR_COLOR_TEMP_KELVIN: 50000,
        },
    )

    await run_powercalc_setup(hass, {})

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

    hass.states.async_set("sensor.availability", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE

    hass.states.async_set("sensor.availability", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "10.00"
