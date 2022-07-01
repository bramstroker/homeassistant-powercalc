"""Config flow for Adaptive Lighting integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_FIXED_RAW,
    CONF_POWER_TEMPLATE,
    DOMAIN,
    CONF_MODE,
    CONF_STANDBY_POWER,
    CONF_DISABLE_STANDBY_POWER,
    CALCULATION_MODES,
    MODE_FIXED,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_POWER,
    CONF_STATES_POWER
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
        vol.Optional(CONF_POWER_TEMPLATE): selector.TemplateSelector(),
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_FIXED_RAW): selector.ObjectSelector()
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    def __init__(self):
        """Initialize options flow."""
        #self.config_entry = config_entry
        self.sensor_config = dict()
        self.name: str = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        if not user_input:
            return self.async_show_form(
                step_id="user", data_schema=CONFIG_SCHEMA,
            )

        self.sensor_config.update(user_input)
        self.name = user_input[CONF_NAME]

        if user_input.get(CONF_MODE) == MODE_FIXED:
            return await self.async_step_fixed()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
            errors={},
        )
    
    async def async_step_fixed(self, user_input: dict[str,str] = None) -> FlowResult:
        if user_input is not None:
            if CONF_FIXED_RAW in user_input:
                fixed_config = user_input[CONF_FIXED_RAW]
            else:
                power = user_input.get(CONF_POWER) or user_input.get(CONF_POWER_TEMPLATE)
                fixed_config = {CONF_POWER: power}

            self.sensor_config.update({CONF_FIXED: fixed_config})
            return self.async_create_entry(
                title=self.name, data=self.sensor_config
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
