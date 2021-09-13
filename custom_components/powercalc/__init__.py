"""The PowerCalc integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.utility_meter.const import (
    DAILY,
    METER_TYPES,
    MONTHLY,
    WEEKLY,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType

from .common import validate_name_pattern
from .const import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_POWER,
    CONF_POWER_SENSOR_NAMING,
    CONF_STATES_POWER,
    CONF_UTILITY_METER_TYPES,
    DATA_CALCULATOR_FACTORY,
    DOMAIN,
    DOMAIN_CONFIG,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
)
from .errors import StrategyConfigurationError, UnsupportedMode
from .light_model import LightModel
from .strategy_fixed import FixedStrategy
from .strategy_interface import PowerCalculationStrategyInterface
from .strategy_linear import LinearStrategy
from .strategy_lut import LutRegistry, LutStrategy

DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
DEFAULT_POWER_NAME_PATTERN = "{} power"
DEFAULT_ENERGY_NAME_PATTERN = "{} energy"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): cv.time_period,
                    vol.Optional(
                        CONF_POWER_SENSOR_NAMING, default=DEFAULT_POWER_NAME_PATTERN
                    ): validate_name_pattern,
                    vol.Optional(
                        CONF_ENERGY_SENSOR_NAMING, default=DEFAULT_ENERGY_NAME_PATTERN
                    ): validate_name_pattern,
                    vol.Optional(CONF_CREATE_ENERGY_SENSORS, default=True): cv.boolean,
                    vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): cv.boolean,
                    vol.Optional(
                        CONF_UTILITY_METER_TYPES, default=[DAILY, WEEKLY, MONTHLY]
                    ): vol.All(cv.ensure_list, [vol.In(METER_TYPES)]),
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistantType, config: dict) -> bool:
    conf = config.get(DOMAIN) or {
        CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
        CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_UTILITY_METERS: False,
    }

    hass.data[DOMAIN] = {
        DATA_CALCULATOR_FACTORY: PowerCalculatorStrategyFactory(hass),
        DOMAIN_CONFIG: conf,
    }

    return True


class PowerCalculatorStrategyFactory:
    def __init__(self, hass: HomeAssistantType) -> None:
        self._hass = hass
        self._lut_registry = LutRegistry()

    def create(
        self,
        config: dict,
        mode: str,
        light_model: Optional[LightModel],
        entity_domain: str,
    ) -> PowerCalculationStrategyInterface:
        """Create instance of calculation strategy based on configuration"""
        if mode == MODE_LINEAR:
            return self._create_linear(config, light_model, entity_domain)

        if mode == MODE_FIXED:
            return self._create_fixed(config, light_model)

        if mode == MODE_LUT:
            return self._create_lut(light_model)

        raise UnsupportedMode("Invalid calculation mode", mode)

    def _create_linear(
        self, config: dict, light_model: LightModel, entity_domain: str
    ) -> LinearStrategy:
        """Create the linear strategy"""
        linear_config = config.get(CONF_LINEAR)

        if linear_config is None and light_model is not None:
            linear_config = light_model.linear_mode_config

        return LinearStrategy(linear_config, entity_domain)

    def _create_fixed(self, config: dict, light_model: LightModel) -> FixedStrategy:
        """Create the fixed strategy"""
        fixed_config = config.get(CONF_FIXED)
        if fixed_config is None and light_model is not None:
            fixed_config = light_model.fixed_mode_config

        power = fixed_config.get(CONF_POWER)
        if isinstance(power, Template):
            power.hass = self._hass

        states_power = fixed_config.get(CONF_STATES_POWER)
        if states_power:
            for p in states_power.values():
                if isinstance(p, Template):
                    p.hass = self._hass

        return FixedStrategy(power, states_power)

    def _create_lut(self, light_model: LightModel) -> LutStrategy:
        """Create the lut strategy"""
        if light_model is None:
            raise StrategyConfigurationError(
                "You must supply a valid manufacturer and model to use the LUT mode"
            )

        return LutStrategy(self._lut_registry, light_model)
