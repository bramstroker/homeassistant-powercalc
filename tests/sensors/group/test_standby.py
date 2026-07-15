from homeassistant.components.mqtt.const import CONF_STATE_CLOSING, CONF_STATE_OPENING
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.const import (
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_OPEN,
    STATE_PLAYING,
    STATE_STANDBY,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_STANDBY_GROUP
from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_STANDBY_POWER,
    CONF_STATES_POWER,
    CONF_UTILITY_METER_TYPES,
    CalculationStrategy,
)
from tests.common import assert_entity_state, run_powercalc_setup, set_states


async def test_standby_group(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "input_boolean.test1",
                CONF_STANDBY_POWER: 0.2,
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 20},
            },
            {
                CONF_ENTITY_ID: "input_boolean.test2",
                CONF_STANDBY_POWER: 0.3,
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 40},
            },
        ],
    )

    await set_states(hass, [("input_boolean.test1", STATE_ON), ("input_boolean.test2", STATE_ON)])
    assert_entity_state(hass, "sensor.all_standby_power", STATE_UNKNOWN)

    energy_state = hass.states.get("sensor.all_standby_energy")
    assert energy_state

    await set_states(hass, [("input_boolean.test1", STATE_OFF), ("input_boolean.test2", STATE_OFF)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.50")

    await set_states(hass, [("input_boolean.test2", STATE_ON)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.20")


async def test_standby_group_utility_meter(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test1",
            CONF_STANDBY_POWER: 0.2,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 20},
        },
        {
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert hass.states.get("sensor.all_standby_energy_daily")


async def test_self_usage_sensors_included(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "switch.test1",
                CONF_STANDBY_POWER: 0.2,
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 20},
            },
            {
                CONF_ENTITY_ID: "switch.test2",
                CONF_MANUFACTURER: "test",
                CONF_MODEL: "smart_switch_with_pm_new",
            },
        ],
    )

    await set_states(hass, [("switch.test1", STATE_ON), ("switch.test2", STATE_ON)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.70")

    await set_states(hass, [("switch.test1", STATE_OFF), ("switch.test2", STATE_OFF)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.50")

    await set_states(hass, [("switch.test1", STATE_ON)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.30")


async def test_cover_and_media_player_entities(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "cover.test1",
                CONF_STANDBY_POWER: 0.2,
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {
                    CONF_STATES_POWER: {
                        CONF_STATE_OPENING: 50,
                        CONF_STATE_CLOSING: 50,
                    },
                },
            },
            {
                CONF_ENTITY_ID: "media_player.test2",
                CONF_STANDBY_POWER: 0.3,
                CONF_MANUFACTURER: "test",
                CONF_MODEL: "media_player",  # standby_power: 1.65
            },
        ],
    )

    await set_states(hass, [("cover.test1", CONF_STATE_OPENING), ("media_player.test2", STATE_PLAYING, {"volume": 20})])
    assert_entity_state(hass, "sensor.all_standby_power", STATE_UNKNOWN)

    await set_states(hass, [("cover.test1", STATE_OPEN)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.20")

    await set_states(hass, [("media_player.test2", STATE_STANDBY)])
    assert_entity_state(hass, "sensor.all_standby_power", "0.50")


async def test_disable_group_creation(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "input_boolean.test1",
            CONF_STANDBY_POWER: 0.2,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 20},
        },
        {
            CONF_CREATE_STANDBY_GROUP: False,
        },
    )

    await set_states(hass, [("input_boolean.test1", STATE_OFF)])
    power_state = hass.states.get("sensor.all_standby_power")
    assert not power_state
