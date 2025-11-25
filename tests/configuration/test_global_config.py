from homeassistant.core import HomeAssistant

from custom_components.powercalc import get_global_configuration
from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_NAMING,
    DEFAULT_ENERGY_NAME_PATTERN,
    DOMAIN,
)
from tests.config_flow.test_global_configuration import create_mock_global_config_entry


async def test_yaml_config_overrides_gui_config(hass: HomeAssistant) -> None:
    gui_config = {
        CONF_CREATE_UTILITY_METERS: False,
        CONF_POWER_SENSOR_NAMING: "foobar",
    }
    create_mock_global_config_entry(hass, gui_config)
    yaml_config = {
        CONF_CREATE_UTILITY_METERS: True,
    }
    final_config = await get_global_configuration(hass, {DOMAIN: yaml_config})

    assert final_config[CONF_CREATE_UTILITY_METERS] is True
    assert final_config[CONF_ENERGY_SENSOR_NAMING] == DEFAULT_ENERGY_NAME_PATTERN
    assert final_config[CONF_POWER_SENSOR_NAMING] == "foobar"
