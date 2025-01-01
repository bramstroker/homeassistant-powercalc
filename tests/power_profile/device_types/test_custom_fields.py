import logging

import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_FIELDS, CONF_MANUFACTURER, CONF_MODEL, DUMMY_ENTITY_ID
from tests.common import get_test_config_dir, run_powercalc_setup


async def test_custom_field_variables_from_yaml_config(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    hass.config.config_dir = get_test_config_dir()

    hass.states.async_set("sensor.test", STATE_ON)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "custom-fields",
            CONF_CUSTOM_FIELDS: {
                "some_entity": "sensor.test",
            },
        },
    )

    assert not caplog.records

    assert hass.states.get("sensor.test_power").state == "20.00"
