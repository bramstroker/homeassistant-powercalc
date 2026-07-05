import logging

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorDeviceClass, SensorStateClass
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_ON,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, State
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
    mock_registry,
    mock_restore_cache,
)

from custom_components.powercalc.const import (
    CONF_COST_SENSOR_FRIENDLY_NAMING,
    CONF_COST_SENSOR_NAMING,
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_COST_SENSORS,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_MULTIPLIER,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_PRICE_SURCHARGE,
    CONF_ENERGY_SENSOR_ID,
    CONF_FIXED,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MAIN_POWER_SENSOR,
    CONF_MODE,
    CONF_POWER,
    CONF_SUBTRACT_ENTITIES,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    DOMAIN_CONFIG,
    SERVICE_CALIBRATE_COST,
    SERVICE_RESET_COST,
    CalculationStrategy,
    GroupType,
)
from custom_components.powercalc.sensors.cost import CostSensor
from custom_components.powercalc.sensors.group.tracked_untracked import TrackedPowerSensorFactory
from tests.common import (
    get_simple_fixed_config,
    mock_sensors_in_registry,
    run_powercalc_setup,
    set_states,
)

_KWH = {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR}


@pytest.fixture(autouse=True)
def set_currency(hass: HomeAssistant) -> None:
    """Set the Home Assistant currency for all cost sensor tests."""
    hass.config.currency = "EUR"


def _assert_cost(hass: HomeAssistant, expected: float, entity_id: str = "sensor.test_cost") -> None:
    state = hass.states.get(entity_id)
    assert state
    assert float(state.state) == pytest.approx(expected)


async def _setup_cost_sensor(
    hass: HomeAssistant,
    sensor_config: dict,
    domain_config: dict,
) -> None:
    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_IGNORE_UNAVAILABLE_STATE: True,
            **sensor_config,
        },
        domain_config,
    )


async def test_cost_sensor_fixed_price(hass: HomeAssistant) -> None:
    """Cost accumulates as energy increases, using a fixed global price."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    cost_state = hass.states.get("sensor.test_cost")
    assert cost_state
    assert cost_state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.MONETARY
    assert cost_state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL
    assert cost_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    _assert_cost(hass, 0)

    await set_states(hass, [("sensor.existing_energy", "15", _KWH)])  # +5 kWh * 0.25
    _assert_cost(hass, 1.25)

    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +5 kWh * 0.25
    _assert_cost(hass, 2.5)


async def test_cost_sensor_fixed_price_with_surcharge(hass: HomeAssistant) -> None:
    """Cost uses the configured fixed price plus surcharge."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25, CONF_ENERGY_PRICE_SURCHARGE: 0.05},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])

    _assert_cost(hass, 3.0)


async def test_cost_sensor_fixed_price_with_surcharge_and_multiplier(hass: HomeAssistant) -> None:
    """Cost applies surcharge before the multiplier."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {
            CONF_ENERGY_PRICE: 0.25,
            CONF_ENERGY_PRICE_SURCHARGE: 0.05,
            CONF_ENERGY_PRICE_MULTIPLIER: 1.2,
        },
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])

    _assert_cost(hass, 3.6)


async def test_cost_sensor_price_at_consumption(hass: HomeAssistant) -> None:
    """A dynamic price sensor prices energy at the price valid when it was consumed."""
    await set_states(hass, [("sensor.energy_price", "0.20")])
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price"},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # +10 kWh * 0.20
    _assert_cost(hass, 2.0)

    await set_states(hass, [("sensor.energy_price", "0.40")])  # price change only
    _assert_cost(hass, 2.0)

    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +10 kWh * 0.40
    _assert_cost(hass, 6.0)


async def test_cost_sensor_price_sensor_with_surcharge(hass: HomeAssistant) -> None:
    """Cost uses the dynamic price sensor value plus surcharge."""
    await set_states(hass, [("sensor.energy_price", "0.20")])
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price", CONF_ENERGY_PRICE_SURCHARGE: 0.05},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])
    _assert_cost(hass, 2.5)

    await set_states(hass, [("sensor.energy_price", "0.40")])
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])
    _assert_cost(hass, 7.0)


async def test_cost_sensor_price_sensor_with_surcharge_and_multiplier(hass: HomeAssistant) -> None:
    """Cost applies surcharge and multiplier to dynamic price sensor values."""
    await set_states(hass, [("sensor.energy_price", "0.20")])
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {
            CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price",
            CONF_ENERGY_PRICE_SURCHARGE: 0.05,
            CONF_ENERGY_PRICE_MULTIPLIER: 1.2,
        },
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])
    _assert_cost(hass, 3.0)

    await set_states(hass, [("sensor.energy_price", "0.40")])
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])
    _assert_cost(hass, 8.4)


async def test_price_change_settles_pending_energy_at_previous_price(hass: HomeAssistant) -> None:
    """A price change settles the energy consumed so far at the previous price."""
    await set_states(hass, [("sensor.energy_price", "0.20")])
    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])
    # Restore a baseline of 100 kWh and pre-set the energy sensor to 110 kWh so 10 kWh is
    # pending (not yet settled by an energy event) when the price changes.
    mock_restore_cache(hass, [State("sensor.test_cost", "0", {"last_energy": "100"})])
    await set_states(hass, [("sensor.existing_energy", "110", _KWH)])

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_CREATE_COST_SENSOR: True,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price"},
    )
    _assert_cost(hass, 0)

    # Changing the price settles the pending 10 kWh at the previous price (0.20), not the new one.
    await set_states(hass, [("sensor.energy_price", "0.40")])
    _assert_cost(hass, 2.0)

    # Further consumption uses the new price.
    await set_states(hass, [("sensor.existing_energy", "120", _KWH)])  # +10 kWh * 0.40
    _assert_cost(hass, 6.0)


async def test_price_change_ignored_when_energy_unavailable(hass: HomeAssistant) -> None:
    """A price change with an unavailable energy sensor does not settle anything."""
    await set_states(hass, [("sensor.energy_price", "0.20"), ("sensor.existing_energy", "unavailable")])
    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])
    mock_restore_cache(hass, [State("sensor.test_cost", "0", {"last_energy": "100"})])

    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_CREATE_COST_SENSOR: True,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price"},
    )

    await set_states(hass, [("sensor.energy_price", "0.40")])  # energy unavailable -> nothing to settle
    _assert_cost(hass, 0)


async def test_price_sensor_unavailable_defers_cost(hass: HomeAssistant) -> None:
    """When the price sensor is unavailable the consumption is priced once it returns."""
    await set_states(hass, [("sensor.energy_price", "unavailable")])
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price"},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # price unavailable -> deferred
    _assert_cost(hass, 0)

    await set_states(hass, [("sensor.energy_price", "0.30")])
    await set_states(hass, [("sensor.existing_energy", "12", _KWH)])  # +12 kWh * 0.30 (10 deferred + 2 new)
    _assert_cost(hass, 3.6)


async def test_per_sensor_toggle_overrides_global(hass: HomeAssistant) -> None:
    """Per-sensor create_cost_sensor overrides the global create_cost_sensors."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: False},
        {CONF_ENERGY_PRICE: 0.25, CONF_CREATE_COST_SENSORS: True},
    )
    assert hass.states.get("sensor.test_cost") is None


async def test_global_toggle_creates_cost_sensor(hass: HomeAssistant) -> None:
    """Enabling create_cost_sensors globally creates a cost sensor without a per-sensor flag."""
    await _setup_cost_sensor(
        hass,
        {},
        {CONF_ENERGY_PRICE: 0.25, CONF_CREATE_COST_SENSORS: True},
    )
    assert hass.states.get("sensor.test_cost") is not None


async def test_cost_sensor_naming_pattern(hass: HomeAssistant) -> None:
    """A global cost_sensor_naming pattern drives the cost sensor name and entity id."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25, CONF_COST_SENSOR_NAMING: "{} energy costs"},
    )

    assert hass.states.get("sensor.test_cost") is None
    state = hass.states.get("sensor.test_energy_costs")
    assert state
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Test energy costs"


async def test_cost_sensor_friendly_naming_pattern(hass: HomeAssistant) -> None:
    """A global cost_sensor_friendly_naming pattern only changes the friendly name."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25, CONF_COST_SENSOR_FRIENDLY_NAMING: "Costs of {}"},
    )

    # Entity id keeps the default naming, only the friendly name follows the pattern.
    state = hass.states.get("sensor.test_cost")
    assert state
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Costs of Test"


async def test_cost_sensor_created_per_utility_meter(hass: HomeAssistant) -> None:
    """A cost sensor is created for the energy sensor and for each utility meter."""
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_COST_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
        {CONF_ENERGY_PRICE: 0.25},
    )

    # Cost sensor for the energy sensor itself.
    assert hass.states.get("sensor.test_cost") is not None

    # Cost sensor for the daily utility meter.
    meter_cost = hass.states.get("sensor.test_energy_daily_cost")
    assert meter_cost
    assert meter_cost.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.MONETARY
    assert meter_cost.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL
    assert meter_cost.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"


async def test_no_utility_meter_cost_sensor_when_meters_disabled(hass: HomeAssistant) -> None:
    """No per-meter cost sensor is created when utility meters are disabled."""
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_COST_SENSOR: True,
        },
        {CONF_ENERGY_PRICE: 0.25},
    )

    assert hass.states.get("sensor.test_cost") is not None
    assert hass.states.get("sensor.test_energy_daily") is None
    assert hass.states.get("sensor.test_energy_daily_cost") is None


async def test_utility_meter_cost_sensor_accumulates(hass: HomeAssistant) -> None:
    """The per-meter cost sensor accumulates the cost of the energy the meter tracks."""
    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_IGNORE_UNAVAILABLE_STATE: True,
            CONF_CREATE_COST_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
        {CONF_ENERGY_PRICE: 0.25},
    )

    meter_cost_id = "sensor.sensor_existing_energy_daily_cost"
    meter_id = "sensor.existing_energy_daily"
    for value in ("10", "20", "30", "40"):
        await set_states(hass, [("sensor.existing_energy", value, _KWH)])

    # The meter tracked 30 kWh (10 -> 40); its cost sensor prices the deltas seen after
    # its first (baseline) reading: (20 kWh) * 0.25 = 5.0.
    assert hass.states.get(meter_id).state == "30.0000"
    _assert_cost(hass, 5.0, meter_cost_id)

    # When the utility meter resets for a new cycle, its cost sensor resets to zero too.
    hass.states.async_set(meter_id, "0", _KWH)
    await hass.async_block_till_done()
    _assert_cost(hass, 0.0, meter_cost_id)

    # A new cycle accumulates from zero again.
    hass.states.async_set(meter_id, "8", _KWH)
    await hass.async_block_till_done()
    _assert_cost(hass, 2.0, meter_cost_id)


async def test_restore_state(hass: HomeAssistant) -> None:
    """The accumulated cost and last energy baseline are restored across restarts."""
    mock_restore_cache(
        hass,
        [
            State("sensor.test_cost", "5.0", {"last_energy": "100"}),
        ],
    )

    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    _assert_cost(hass, 5.0)

    # last_energy was restored as 100, so only the delta above 100 is priced.
    await set_states(hass, [("sensor.existing_energy", "110", _KWH)])  # +10 kWh * 0.25
    _assert_cost(hass, 7.5)


async def test_cost_sensor_handles_energy_reset(hass: HomeAssistant) -> None:
    """A decreasing energy value (reset) is treated as the new delta."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +10 kWh * 0.25
    _assert_cost(hass, 2.5)

    await set_states(hass, [("sensor.existing_energy", "5", _KWH)])  # reset -> 5 kWh * 0.25
    _assert_cost(hass, 3.75)


async def test_reset_cost_service(hass: HomeAssistant) -> None:
    """The cost reset service resets accumulated cost and starts from the current energy baseline."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])
    _assert_cost(hass, 2.5)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESET_COST,
        {ATTR_ENTITY_ID: "sensor.test_cost"},
        blocking=True,
    )

    _assert_cost(hass, 0)
    cost_state = hass.states.get("sensor.test_cost")
    assert cost_state
    assert cost_state.attributes["last_energy"] == "10"

    await set_states(hass, [("sensor.existing_energy", "12", _KWH)])
    _assert_cost(hass, 0.5)


async def test_calibrate_cost_service(hass: HomeAssistant) -> None:
    """The cost calibrate service sets accumulated cost and starts from the current energy baseline."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_COST,
        {ATTR_ENTITY_ID: "sensor.test_cost", "value": "7"},
        blocking=True,
    )

    _assert_cost(hass, 7)
    cost_state = hass.states.get("sensor.test_cost")
    assert cost_state
    assert cost_state.attributes["last_energy"] == "10"

    await set_states(hass, [("sensor.existing_energy", "12", _KWH)])
    _assert_cost(hass, 7.5)


async def test_cost_sensor_ignores_invalid_energy_states(hass: HomeAssistant) -> None:
    """Unavailable, unknown and non-numeric energy states do not affect the cost."""
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "unavailable", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "unknown", _KWH)])
    await set_states(hass, [("sensor.existing_energy", "not_a_number", _KWH)])
    _assert_cost(hass, 0)

    await set_states(hass, [("sensor.existing_energy", "15", _KWH)])  # +5 kWh * 0.25
    _assert_cost(hass, 1.25)


async def test_price_sensor_invalid_value_defers_cost(hass: HomeAssistant) -> None:
    """A non-numeric price sensor value defers the cost until a valid price is available."""
    await set_states(hass, [("sensor.energy_price", "invalid")])
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price"},
    )

    await set_states(hass, [("sensor.existing_energy", "0", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # invalid price -> deferred
    _assert_cost(hass, 0)

    await set_states(hass, [("sensor.energy_price", "0.30")])
    await set_states(hass, [("sensor.existing_energy", "12", _KWH)])  # +12 kWh * 0.30
    _assert_cost(hass, 3.6)


async def test_restore_invalid_state(hass: HomeAssistant) -> None:
    """An invalid restored state falls back to zero."""
    mock_restore_cache(
        hass,
        [
            State("sensor.test_cost", "invalid"),
        ],
    )

    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {CONF_ENERGY_PRICE: 0.25},
    )

    _assert_cost(hass, 0)


async def test_no_cost_sensor_without_price(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No cost sensor is created when no energy price is configured."""
    caplog.set_level(logging.WARNING)
    await _setup_cost_sensor(
        hass,
        {CONF_CREATE_COST_SENSOR: True},
        {},
    )
    assert hass.states.get("sensor.test_cost") is None
    assert "no energy price is configured" in caplog.text


async def test_cost_sensor_name_derived_from_source(hass: HomeAssistant) -> None:
    """When no name is configured the cost sensor name is derived from the source entity."""
    mock_sensors_in_registry(hass, energy_entities=["sensor.existing_energy"])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_CREATE_COST_SENSOR: True,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {CONF_ENERGY_PRICE: 0.25},
    )
    assert hass.states.get("sensor.dummy_cost") is not None


async def test_cost_sensor_reuses_existing_entity_id(hass: HomeAssistant) -> None:
    """An already registered cost sensor entity id is reused."""
    mock_registry(
        hass,
        {
            "sensor.existing_energy": RegistryEntryWithDefaults(
                entity_id="sensor.existing_energy",
                unique_id="sensor.existing_energy",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
            "sensor.preexisting_cost": RegistryEntryWithDefaults(
                entity_id="sensor.preexisting_cost",
                unique_id="sensor.existing_energy_cost",
                platform=DOMAIN,
            ),
        },
    )
    await run_powercalc_setup(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            CONF_CREATE_COST_SENSOR: True,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
        {CONF_ENERGY_PRICE: 0.25},
    )
    assert hass.states.get("sensor.preexisting_cost") is not None


async def test_cost_sensor_for_custom_group(hass: HomeAssistant) -> None:
    """A cost sensor is created for a custom group energy sensor."""
    await set_states(hass, [("input_boolean.test1", STATE_ON), ("input_boolean.test2", STATE_ON)])
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_CREATE_COST_SENSOR: True,
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 10),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
        {CONF_ENERGY_PRICE: 0.25},
    )
    assert hass.states.get("sensor.testgroup_cost") is not None


async def test_cost_sensor_for_subtract_group(hass: HomeAssistant) -> None:
    """A cost sensor is created for a subtract group energy sensor."""
    await set_states(hass, [("sensor.a_power", 100), ("sensor.b_power", 20)])
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test",
            CONF_GROUP_TYPE: GroupType.SUBTRACT,
            CONF_ENTITY_ID: "sensor.a_power",
            CONF_SUBTRACT_ENTITIES: ["sensor.b_power"],
            CONF_CREATE_COST_SENSOR: True,
        },
        {CONF_ENERGY_PRICE: 0.25},
    )
    assert hass.states.get("sensor.test_cost") is not None


async def test_cost_sensors_for_tracked_untracked_group(hass: HomeAssistant) -> None:
    """Cost sensors are created for both the tracked and untracked energy sensors."""
    hass.data[DOMAIN] = {DOMAIN_CONFIG: {CONF_ENERGY_PRICE: 0.25}}
    factory = TrackedPowerSensorFactory(
        hass,
        MockConfigEntry(),
        {
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power", "sensor.main_power"],
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_COST_SENSOR: True,
        },
    )
    sensors = await factory.create_tracked_untracked_group_sensors()

    cost_sensors = [sensor for sensor in sensors if isinstance(sensor, CostSensor)]
    assert {sensor.entity_id for sensor in cost_sensors} == {"sensor.tracked_cost", "sensor.untracked_cost"}
