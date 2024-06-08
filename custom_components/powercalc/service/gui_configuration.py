import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from custom_components.powercalc import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_IGNORE_UNAVAILABLE_STATE,
    DOMAIN,
    ENERGY_INTEGRATION_METHODS,
)
from custom_components.powercalc.const import CONF_CREATE_ENERGY_SENSOR

ALLOWED_CONFIG_KEYS = [
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_ENERGY_INTEGRATION_METHOD,
]

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("field"): vol.In(ALLOWED_CONFIG_KEYS),
        vol.Required("value"): cv.string,
    },
)


async def change_gui_configuration(hass: HomeAssistant, call: ServiceCall) -> None:
    field = call.data["field"]
    value = call.data["value"]

    if field in [
        CONF_CREATE_ENERGY_SENSOR,
        CONF_CREATE_UTILITY_METERS,
        CONF_IGNORE_UNAVAILABLE_STATE,
    ]:
        value = cv.boolean(value)

    if field == CONF_ENERGY_INTEGRATION_METHOD and value not in ENERGY_INTEGRATION_METHODS:
        raise HomeAssistantError(f"Invalid integration method {value}")

    for entry in hass.config_entries.async_entries(DOMAIN):
        if field not in entry.data:
            continue
        new_data = entry.data.copy()
        new_data[field] = value
        hass.config_entries.async_update_entry(entry, data=new_data)
