import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_GROUP_TYPE,
    CONF_SUBTRACT_ENTITIES,
    GroupType,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.sensors.group.subtract import validate_config
from tests.common import (
    run_powercalc_setup,
)


async def test_subtract_sensor(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.a_power", 100)
    hass.states.async_set("sensor.b_power", 20)
    hass.states.async_set("sensor.c_power", 25)

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test",
            CONF_GROUP_TYPE: GroupType.SUBTRACT,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_ENTITY_ID: "sensor.a_power",
            CONF_SUBTRACT_ENTITIES: [
                "sensor.b_power",
                "sensor.c_power",
            ],
        },
    )

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "55.00"

    hass.states.async_set("sensor.b_power", 22.45)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state.state == "52.55"

    assert hass.states.get("sensor.test_energy_daily")


async def test_base_sensor_state_none(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.b_power", 20)

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test",
            CONF_GROUP_TYPE: GroupType.SUBTRACT,
            CONF_ENTITY_ID: "sensor.a_power",
            CONF_SUBTRACT_ENTITIES: [
                "sensor.b_power",
            ],
        },
    )

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "config,valid",
    [
        (
            {
                CONF_NAME: "Test",
                CONF_SUBTRACT_ENTITIES: [
                    "sensor.b_power",
                    "sensor.c_power",
                ],
            },
            False,
        ),
        (
            {
                CONF_NAME: "Test",
                CONF_ENTITY_ID: "sensor.a_power",
            },
            False,
        ),
        (
            {
                CONF_ENTITY_ID: "sensor.a_power",
                CONF_SUBTRACT_ENTITIES: [
                    "sensor.b_power",
                    "sensor.c_power",
                    "sensor.d_power",
                ],
            },
            False,
        ),
        (
            {
                CONF_NAME: "Test",
                CONF_ENTITY_ID: "sensor.a_power",
                CONF_SUBTRACT_ENTITIES: [
                    "sensor.b_power",
                    "sensor.c_power",
                    "sensor.d_power",
                ],
            },
            True,
        ),
    ],
)
async def test_validate(config: ConfigType, valid: bool) -> None:
    if not valid:
        with pytest.raises(SensorConfigurationError):
            validate_config(config)
    else:
        validate_config(config)
