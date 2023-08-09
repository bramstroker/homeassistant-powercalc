import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
)
from custom_components.powercalc.common import get_merged_sensor_configuration
from custom_components.powercalc.const import CONF_CREATE_ENERGY_SENSOR


@pytest.mark.parametrize(
    "configs,output_config",
    [
        (
            [
                {
                    CONF_CREATE_UTILITY_METERS: True,
                    CONF_CREATE_ENERGY_SENSORS: False,
                },
                {
                    CONF_ENTITY_ID: "switch.test",
                    CONF_CREATE_UTILITY_METERS: False,
                },
            ],
            {
                CONF_ENTITY_ID: "switch.test",
                CONF_CREATE_ENERGY_SENSORS: False,
                CONF_CREATE_ENERGY_SENSOR: False,
                CONF_CREATE_UTILITY_METERS: False,
            },
        ),
        (
            [
                {
                    CONF_NAME: "foo",
                },
                {
                    CONF_ENTITY_ID: "switch.test",
                },
            ],
            {
                CONF_ENTITY_ID: "switch.test",
                CONF_CREATE_ENERGY_SENSOR: None,
            },
        ),
    ],
)
async def test_merge_configuration(
    hass: HomeAssistant,
    configs: list[dict],
    output_config: dict,
) -> None:
    assert get_merged_sensor_configuration(*configs) == output_config
