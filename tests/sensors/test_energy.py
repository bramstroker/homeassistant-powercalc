from datetime import timedelta
import logging
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt
import pytest

from custom_components.powercalc import CONF_ENERGY_UPDATE_INTERVAL
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DOMAIN,
    SERVICE_CALIBRATE_ENERGY,
    UnitPrefix,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from tests.common import (
    assert_entity_state,
    async_advance_time,
    get_simple_fixed_config,
    mock_device,
    mock_entities_in_registry,
    mock_sensors_in_registry,
    run_powercalc_setup,
    set_states,
)


async def test_related_energy_sensor_is_used_for_existing_power_sensor(hass: HomeAssistant) -> None:
    mock_device(hass, "shelly-device-id", "Shelly", "Plug S")

    mock_entities_in_registry(
        hass,
        {
            "sensor.existing_power": {"device_id": "shelly-device-id", "device_class": SensorDeviceClass.POWER},
            "sensor.existing_energy": {"device_id": "shelly-device-id", "device_class": SensorDeviceClass.ENERGY},
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
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    assert_entity_state(
        hass,
        "sensor.testgroup_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.existing_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.testgroup_energy",
        attributes={
            ATTR_ENTITIES: {
                "sensor.existing_energy",
            },
        },
    )


async def test_force_create_energy_sensor_for_existing_power_sensor(
    hass: HomeAssistant,
) -> None:
    """
    When the user uses `power_sensor_id` option and a related energy sensor already exists in the system,
    creation can be forced with `force_energy_sensor_creation`
    """

    mock_device(hass, "shelly-device-id", "Shelly", "Plug S")

    mock_entities_in_registry(
        hass,
        {
            "sensor.existing_power": {"device_id": "shelly-device-id", "device_class": SensorDeviceClass.POWER},
            "sensor.existing_energy": {"device_id": "shelly-device-id", "device_class": SensorDeviceClass.ENERGY},
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_NAME: "MySensor",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                    CONF_FORCE_ENERGY_SENSOR_CREATION: True,
                },
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    assert_entity_state(
        hass,
        "sensor.testgroup_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.existing_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.testgroup_energy",
        attributes={
            ATTR_ENTITIES: {
                "sensor.mysensor_energy",
            },
        },
    )


async def test_force_create_energy_sensor_overrides_create_energy_sensors_option(hass: HomeAssistant) -> None:
    """
    When you use force_energy_sensor_creation, it should override create_energy_sensors option,
    and create an energy sensor
    """
    mock_entities_in_registry(
        hass,
        {
            "sensor.bedroom_airco_power": {"device_class": SensorDeviceClass.POWER},
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_POWER_SENSOR_ID: "sensor.bedroom_airco_power",
            CONF_NAME: "Bedroom airco",
            CONF_FORCE_ENERGY_SENSOR_CREATION: True,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {
            CONF_CREATE_ENERGY_SENSORS: False,
        },
    )

    energy_state = hass.states.get("sensor.bedroom_airco_energy")
    assert energy_state


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_DISABLE_EXTENDED_ATTRIBUTES: True},
    )

    energy_state = hass.states.get("sensor.test_energy")
    assert ATTR_SOURCE_DOMAIN not in energy_state.attributes
    assert ATTR_SOURCE_ENTITY not in energy_state.attributes


async def test_rounding_precision(hass: HomeAssistant) -> None:
    # The source entity needs a unique id, otherwise the energy sensor is not registered.
    entity_registry = mock_entities_in_registry(hass, {"input_boolean.test": {}})
    await set_states(hass, [("input_boolean.test", STATE_OFF)])

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_ENERGY_SENSOR_PRECISION: 2},
    )

    energy_entry = entity_registry.async_get("sensor.test_energy")
    assert energy_entry
    assert energy_entry.options == {"sensor": {"suggested_display_precision": 2}}


async def test_real_energy_sensor(hass: HomeAssistant) -> None:
    """Test user can refer an existing real energy sensor to create utility meters for it or add to group with YAML"""

    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
                },
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    await hass.async_block_till_done()
    assert_entity_state(
        hass,
        "sensor.testgroup_energy",
        attributes={
            ATTR_ENTITIES: {
                "sensor.existing_energy",
            },
        },
    )


async def test_real_energy_sensor_error_on_non_existing_entity(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that an error is logged when user supplies unknown entity id in energy_sensor_id"""

    caplog.set_level(logging.ERROR)

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_ENERGY_SENSOR_ID: "sensor.invalid_energy",
                },
            ],
        },
    )

    assert "No energy sensor with id" in caplog.text


@pytest.mark.parametrize(
    "domain_config, expected_unit",
    [
        pytest.param({CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE}, UnitOfEnergy.WATT_HOUR, id="none"),
        # Without an explicit prefix it defaults to k, so a W power sensor yields a kWh energy sensor.
        pytest.param({}, UnitOfEnergy.KILO_WATT_HOUR, id="kilo by default"),
    ],
)
async def test_unit_prefix(hass: HomeAssistant, domain_config: ConfigType, expected_unit: str) -> None:
    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        domain_config,
    )

    await async_advance_time(hass, timedelta(hours=1), block=False)

    await set_states(hass, [("sensor.test_power", "50.00", {ATTR_UNIT_OF_MEASUREMENT: "W"})])
    assert_entity_state(hass, "sensor.test_energy", attributes={ATTR_UNIT_OF_MEASUREMENT: expected_unit})


def test_set_entity_category(hass: HomeAssistant) -> None:
    energy_sensor = VirtualEnergySensor(
        hass=hass,
        source_entity="sensor.test_power",
        entity_id="sensor.test_energy",
        name="Test energy",
        unit_prefix="k",
        unique_id="1234",
        entity_category=EntityCategory(EntityCategory.DIAGNOSTIC),
        powercalc_source_entity="light.test",
        powercalc_source_domain="light",
        sensor_config={},
    )
    assert energy_sensor.entity_category == EntityCategory.DIAGNOSTIC


async def test_calibrate_service(hass: HomeAssistant) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test"),
    )
    entity_id = "sensor.test_energy"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_ENERGY,
        {
            ATTR_ENTITY_ID: entity_id,
            "value": "100",
        },
        blocking=True,
    )

    assert_entity_state(hass, entity_id, "100.0000")


async def test_real_power_sensor_kw(hass: HomeAssistant) -> None:
    """
    Test that the riemann integral sensor is correctly created and updated for a kW power sensor
    Fixes https://github.com/bramstroker/homeassistant-powercalc/issues/1676
    """

    mock_entities_in_registry(
        hass,
        {
            "sensor.test_power": {
                "device_class": SensorDeviceClass.POWER,
                "unit_of_measurement": UnitOfPower.KILO_WATT,
            },
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_UNIQUE_ID: "1234353",
            CONF_POWER_SENSOR_ID: "sensor.test_power",
        },
    )

    await set_states(
        hass,
        [
            (
                "sensor.test_power",
                "100",
                {
                    ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
                    ATTR_DEVICE_CLASS: SensorDeviceClass.POWER,
                    ATTR_STATE_CLASS: SensorStateClass.MEASUREMENT,
                },
            ),
        ],
    )
    state = hass.states.get("sensor.test_energy")
    assert state

    now = dt.utcnow() + timedelta(minutes=60)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        await set_states(
            hass,
            [
                (
                    "sensor.test_power",
                    "200",
                    {
                        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
                        ATTR_DEVICE_CLASS: SensorDeviceClass.POWER,
                        ATTR_STATE_CLASS: SensorStateClass.MEASUREMENT,
                    },
                ),
            ],
        )
    assert_entity_state(hass, "sensor.test_energy", attributes={ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})


async def test_real_power_sensor_invalid_unit(hass: HomeAssistant) -> None:
    """Test that an invalid unit on the source power sensor falls back gracefully."""
    mock_entities_in_registry(
        hass,
        {
            "sensor.test_power": {"device_class": SensorDeviceClass.POWER, "unit_of_measurement": "bogus_unit"},
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_UNIQUE_ID: "1234353",
            CONF_POWER_SENSOR_ID: "sensor.test_power",
        },
    )

    state = hass.states.get("sensor.test_energy")
    assert state


async def test_device_class_is_set_after_startup(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1887"""
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_UNIQUE_ID: "1234353",
            CONF_POWER_SENSOR_ID: "sensor.test_power",
        },
    )

    assert_entity_state(hass, "sensor.test_energy", attributes={ATTR_DEVICE_CLASS: SensorDeviceClass.ENERGY})


async def test_force_updated_at_interval(hass: HomeAssistant) -> None:
    """
    Make sure energy_update_interval is respected.
    Energy sensor should update at the defined interval even when power sensor state does not change.
    """
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_UNIQUE_ID: "1234353",
            CONF_POWER_SENSOR_ID: "sensor.test_power",
        },
        {
            CONF_ENERGY_UPDATE_INTERVAL: 20,
        },
    )

    power_sensor_id = "sensor.test_power"
    energy_sensor_id = "sensor.test_energy"

    await set_states(hass, [(power_sensor_id, "100", {ATTR_UNIT_OF_MEASUREMENT: "W"})])
    await async_advance_time(hass, timedelta(minutes=60), block=False)
    assert_entity_state(hass, energy_sensor_id, "0.1000")
    await async_advance_time(hass, 40, block=False)
    assert_entity_state(hass, energy_sensor_id, "0.1011")


async def test_outlier_filtering(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    power_sensor_id = "sensor.test_power"
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_FILTER_OUTLIER_ENABLED: True,
        },
    )

    await set_states(
        hass,
        [
            (power_sensor_id, "100", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "120", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "500", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "1200", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "200", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "400", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "7000000", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "500", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "1100", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "20", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
            (power_sensor_id, "80", {ATTR_UNIT_OF_MEASUREMENT: "W"}),
        ],
    )
    assert "Rejecting power value 7000000 as outlier for energy integration" in caplog.text


@pytest.mark.parametrize("interruption", [STATE_UNAVAILABLE, STATE_UNKNOWN, "foo"])
async def test_outlier_filtering_handles_non_numeric_states(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    interruption: str,
) -> None:
    """A non numeric power state must pass through the outlier filter untouched.

    It also must not clear the pending rejection: when the source recovers, the substitution
    of the previously rejected outlier still has to happen.
    """
    caplog.set_level(logging.DEBUG)

    power_sensor_id = "sensor.test_power"
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_FILTER_OUTLIER_ENABLED: True,
        },
    )

    async def advance_and_set(value: str) -> None:
        freezer.tick(timedelta(seconds=15))
        await set_states(hass, [(power_sensor_id, value, {ATTR_UNIT_OF_MEASUREMENT: "W"})])

    for value in ["4.4", "4.1", "4.6", "4.2", "4.5", "4.4", "4.5", "4.1", "4.0", "4.2"]:
        await advance_and_set(value)

    energy_before = float(hass.states.get("sensor.test_energy").state)

    # Spike, then the source drops out before returning to the baseline
    await advance_and_set("6553.5")
    await advance_and_set(interruption)
    await advance_and_set("4.0")

    energy_after = float(hass.states.get("sensor.test_energy").state)

    assert "Rejecting power value 6553.5 as outlier for energy integration" in caplog.text
    assert energy_after - energy_before < 0.001


async def test_outlier_filtering_does_not_leak_energy(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Regression test for https://github.com/bramstroker/homeassistant-powercalc/issues/4279.

    With the default `left` Riemann integration method the harmful contribution of an outlier
    is not on its own state change (it becomes the new_state), but on the *following* state
    change when it acts as the old_state. Ensure the spike never leaks into the energy total.
    """
    caplog.set_level(logging.DEBUG)

    power_sensor_id = "sensor.test_power"
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_POWER_SENSOR_ID: power_sensor_id,
            CONF_ENERGY_FILTER_OUTLIER_ENABLED: True,
        },
    )

    async def advance_and_set(value: str) -> None:
        freezer.tick(timedelta(seconds=15))
        await set_states(hass, [(power_sensor_id, value, {ATTR_UNIT_OF_MEASUREMENT: "W"})])

    # Warm up the filter with a stable but slightly varied ~4W baseline (non-zero MAD)
    for value in ["4.4", "4.1", "4.6", "4.2", "4.5", "4.4", "4.5", "4.1", "4.0", "4.2"]:
        await advance_and_set(value)

    energy_before = float(hass.states.get("sensor.test_energy").state)

    # Spike to an unrealistic value and back to the baseline
    await advance_and_set("6553.5")
    await advance_and_set("4.0")

    energy_after = float(hass.states.get("sensor.test_energy").state)

    assert "Rejecting power value 6553.5 as outlier for energy integration" in caplog.text
    # The spike (6553.5W integrated over 15s ~= 0.027 kWh) must not have leaked into the total.
    # Only the ~4W baseline over the two intervals (~0.00003 kWh) may have accrued.
    assert energy_after - energy_before < 0.001
