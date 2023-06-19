from datetime import timedelta

from homeassistant.const import ATTR_ENTITY_ID, CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.powercalc.const import (
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_ACTIVATE_PLAYBOOK,
)
from tests.common import get_test_config_dir, run_powercalc_setup


async def test_activate_playbook_service(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "playbooks/test.csv",
                },
            },
        },
    )
    hass.config.config_dir = get_test_config_dir()

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
