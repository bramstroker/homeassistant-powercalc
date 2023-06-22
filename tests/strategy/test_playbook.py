from datetime import timedelta

import pytest
from homeassistant.const import ATTR_ENTITY_ID, CONF_ENTITY_ID, CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.powercalc.const import (
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_STANDBY_POWER,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_ACTIVATE_PLAYBOOK,
    SERVICE_STOP_PLAYBOOK,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.playbook import PlaybookStrategy
from tests.common import get_simple_fixed_config, get_test_config_dir, run_powercalc_setup


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

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_PLAYBOOK,
        {ATTR_ENTITY_ID: "sensor.test_power", "playbook_id": "playbook1"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.00"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=1.5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.50"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "40.00"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=4.5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "60.00"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=6.5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.20"


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

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_PLAYBOOK,
        {ATTR_ENTITY_ID: "sensor.test_power", "playbook_id": "playbook1"},
        blocking=True,
    )
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=1.5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.50"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_STOP_PLAYBOOK,
        {ATTR_ENTITY_ID: "sensor.test_power"},
        blocking=True,
    )
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.50"

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=4.5))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "20.50"


async def test_turn_off_stops_running_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.washing_machine",
            CONF_STANDBY_POWER: 0.5,
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                },
            },
        },
    )

    hass.states.async_set("switch.washing_machine", STATE_ON)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ACTIVATE_PLAYBOOK,
        {ATTR_ENTITY_ID: "sensor.washing_machine_power", "playbook_id": "playbook1"},
        blocking=True,
    )
    await hass.async_block_till_done()

    hass.states.async_set("switch.washing_machine", STATE_OFF)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.washing_machine_power").state == "0.50"


async def test_services_raises_error_on_non_playbook_sensor(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("switch.test"),
    )
    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ACTIVATE_PLAYBOOK,
            {ATTR_ENTITY_ID: "sensor.test_power", "playbook_id": "playbook1"},
            blocking=True,
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_STOP_PLAYBOOK,
            {ATTR_ENTITY_ID: "sensor.test_power"},
            blocking=True,
        )
        await hass.async_block_till_done()


async def test_exception_when_providing_unknown_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "test.csv"}})
    with pytest.raises(StrategyConfigurationError):
        await strategy.activate_playbook("program2")


async def test_exception_when_providing_unknown_playbook_file(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "unknown.csv"}})
    with pytest.raises(StrategyConfigurationError):
        await strategy.activate_playbook("program1")


async def test_lazy_load_playbook(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    strategy = PlaybookStrategy(hass, {CONF_PLAYBOOKS: {"program1": "test.csv"}})
    await strategy.activate_playbook("program1")
    await strategy.activate_playbook("program1")

