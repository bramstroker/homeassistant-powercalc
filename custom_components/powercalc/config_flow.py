"""Config flow for Adaptive Lighting integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    DOMAIN,
    CONF_MODE,
    CONF_STANDBY_POWER,
    CONF_DISABLE_STANDBY_POWER,
    CALCULATION_MODES,
    MODE_FIXED,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_POWER
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): str,
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
    vol.Optional(CONF_MODE, default=MODE_FIXED): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=CALCULATION_MODES,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    ),
    vol.Optional(CONF_STANDBY_POWER): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_POWER, default=False): cv.boolean,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR, default=True): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS, default=True): cv.boolean
})

FIXED_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POWER): selector.TemplateSelector(),
        # vol.Optional(CONF_STATES_POWER): vol.Schema(
        #     {cv.string: vol.Any(vol.Coerce(float), cv.template)}
        # ),
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if not user_input:
            return self.async_show_form(
                step_id="user", data_schema=CONFIG_SCHEMA,
            )

        if user_input.get(CONF_MODE) == MODE_FIXED:
            return await self.async_step_fixed(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
            errors={},
        )
    
    async def async_step_fixed(self, user_input: dict[str,str] = None):
        if user_input is not None:
            name = user_input.get(CONF_NAME)
            sensor_config = self.build_sensor_config(user_input)
            sensor_config[CONF_FIXED] = {
                CONF_POWER: 40
            }
            return self.async_create_entry(
                title=name, data=sensor_config
            )

        return self.async_show_form(
            step_id="fixed",
            data_schema=FIXED_SCHEMA,
            errors={},
        )

    def build_sensor_config(self, user_input: dict[str, str]) -> dict[str, str]:
        sensor_config = {
            k: v
            for k, v in user_input.items()
        }
        return sensor_config
