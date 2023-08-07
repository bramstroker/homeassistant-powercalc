from datetime import timedelta

import pytest
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.powercalc.const import (
    CONF_AUTOSTART,
    CONF_MULTIPLY_FACTOR,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_REPEAT,
    CONF_STANDBY_POWER,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_ACTIVATE_PLAYBOOK,
    SERVICE_STOP_PLAYBOOK,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.playbook import PlaybookStrategy
from tests.common import (
    get_simple_fixed_config,
    get_test_config_dir,
    run_powercalc_setup,
)

POWER_SENSOR_ID = "sensor.test_power"


async def test_activate_playbook_service(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                },
            },
        },
    )

    assert hass.states.get("sensor.test_power").state == "0.00"

    await _activate_playbook(hass, "playbook1")

    await elapse_and_assert_power(hass, 1.5, "20.50")
    await elapse_and_assert_power(hass, 3, "40.00")
    await elapse_and_assert_power(hass, 4.5, "60.00")
    await elapse_and_assert_power(hass, 6.5, "20.20")


async def test_stop_playbook_service(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                },
            },
        },
    )

    # Calling stop on a non running playbook should not raise an error.
    await _stop_playbook(hass)

    await _activate_playbook(hass, "playbook1")

    await elapse_and_assert_power(hass, 1.5, "20.50")

    await _stop_playbook(hass)

    await elapse_and_assert_power(hass, 3, "20.50")
    await elapse_and_assert_power(hass, 4.5, "20.50")


async def test_turn_off_stops_running_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_STANDBY_POWER: 0.5,
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                },
            },
        },
    )

    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    await _activate_playbook(hass, "playbook1")

    hass.states.async_set("switch.test", STATE_OFF)
    await hass.async_block_till_done()

    await elapse_and_assert_power(hass, 3, "0.50")


async def test_services_raises_error_on_non_playbook_sensor(
    hass: HomeAssistant,
) -> None:
    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("switch.test"),
    )
    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await _activate_playbook(hass, "playbook1")
        await _stop_playbook(hass)


async def test_repeat(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook": "test2.csv",
                },
                CONF_REPEAT: True,
            },
        },
    )

    await _activate_playbook(hass, "playbook")

    assert hass.states.get("sensor.test_power").state == "0.00"

    await elapse_and_assert_power(hass, 2, "20.00")
    await elapse_and_assert_power(hass, 4, "40.00")
    await elapse_and_assert_power(hass, 6, "20.00")
    await elapse_and_assert_power(hass, 8, "40.00")
    await elapse_and_assert_power(hass, 10, "20.00")

    await _stop_playbook(hass)

    await elapse_and_assert_power(hass, 12, "20.00")
    await elapse_and_assert_power(hass, 14, "20.00")


async def test_autostart(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook": "test2.csv",
                },
                CONF_AUTOSTART: "playbook",
            },
        },
    )

    await elapse_and_assert_power(hass, 2, "20.00")
    await elapse_and_assert_power(hass, 4, "40.00")


async def test_exception_when_providing_unknown_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "test.csv"}})
    with pytest.raises(StrategyConfigurationError):
        await strategy.activate_playbook("program2")


async def test_exception_when_providing_unknown_playbook_file(
    hass: HomeAssistant,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "unknown.csv"}})
    with pytest.raises(StrategyConfigurationError):
        await strategy.activate_playbook("program1")


async def test_exception_on_invalid_csv(
    hass: HomeAssistant,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "invalid.csv"}})
    with pytest.raises(StrategyConfigurationError):
        await strategy.activate_playbook("program1")


async def test_lazy_load_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "test.csv"}})
    await strategy.activate_playbook("program1")
    await strategy.activate_playbook("program1")


async def test_load_csv_from_subdirectory(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "subdir/test.csv",
                },
            },
        },
    )

    await _activate_playbook(hass, "playbook1")

    await elapse_and_assert_power(hass, 2, "20.00")


async def test_multiply_factor(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook": "test2.csv",
                },
            },
            CONF_MULTIPLY_FACTOR: 3,
        },
    )

    await _activate_playbook(hass, "playbook")

    await elapse_and_assert_power(hass, 2, "60.00")


async def elapse_and_assert_power(
    hass: HomeAssistant,
    seconds: float,
    expected_power: str,
) -> None:
    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()

    assert hass.states.get(POWER_SENSOR_ID).state == expected_power


async def _activate_playbook(hass: HomeAssistant, playbook_id: str) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_PLAYBOOK,
        {ATTR_ENTITY_ID: POWER_SENSOR_ID, "playbook_id": playbook_id},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _stop_playbook(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_STOP_PLAYBOOK,
        {ATTR_ENTITY_ID: POWER_SENSOR_ID},
        blocking=True,
    )
    await hass.async_block_till_done()
