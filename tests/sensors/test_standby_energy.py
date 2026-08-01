from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.integration.sensor import ATTR_SOURCE_ID
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_GROUP,
    CONF_CREATE_STANDBY_ENERGY_SENSOR,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_STANDBY_ENERGY_SENSOR_NAMING,
    CONF_STANDBY_POWER,
    CalculationStrategy,
)
from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_standby_energy_sensor_tracks_only_standby_consumption(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_CREATE_STANDBY_ENERGY_SENSOR: True,
            CONF_STANDBY_POWER: 0.5,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    standby_energy = hass.states.get("sensor.test_standby_energy")
    assert standby_energy
    assert standby_energy.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENERGY
    assert standby_energy.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert standby_energy.attributes[ATTR_SOURCE_ID] == "sensor.test_power"
    assert standby_energy.attributes[ATTR_SOURCE_ENTITY] == "input_boolean.test"
    assert not hass.states.get("sensor.test_energy")

    freezer.tick(timedelta(hours=1))
    await set_states(hass, [("input_boolean.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_standby_energy", "0.0005")

    freezer.tick(timedelta(hours=1))
    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    assert_entity_state(hass, "sensor.test_standby_energy", "0.0005")

    freezer.tick(timedelta(hours=1))
    await set_states(hass, [("input_boolean.test", STATE_ON)])
    assert_entity_state(hass, "sensor.test_standby_energy", "0.0010")


async def test_standby_energy_sensor_updates_at_interval_without_source_state_change(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_CREATE_STANDBY_ENERGY_SENSOR: True,
            CONF_STANDBY_POWER: 0.5,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        {CONF_ENERGY_UPDATE_INTERVAL: 20},
    )

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert_entity_state(hass, "sensor.test_standby_energy", "0.0005")


async def test_standby_energy_sensor_custom_naming(hass: HomeAssistant) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_CREATE_STANDBY_ENERGY_SENSOR: True,
            CONF_STANDBY_ENERGY_SENSOR_NAMING: "{} idle consumption",
            CONF_STANDBY_POWER: 0.5,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    assert hass.states.get("sensor.test_idle_consumption")


async def test_standby_energy_sensor_is_excluded_from_energy_group(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    await set_states(hass, [("input_boolean.test", STATE_OFF)])
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test group",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test",
                    CONF_CREATE_STANDBY_ENERGY_SENSOR: True,
                    CONF_STANDBY_POWER: 0.5,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 50},
                },
            ],
        },
    )

    freezer.tick(timedelta(hours=1))
    await set_states(hass, [("input_boolean.test", STATE_ON)])

    group_energy = hass.states.get("sensor.test_group_energy")
    assert group_energy
    assert group_energy.attributes[ATTR_ENTITIES] == {"sensor.test_energy"}
