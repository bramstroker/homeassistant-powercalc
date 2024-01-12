from __future__ import annotations

import logging
from decimal import Decimal

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components import fan, light, media_player
from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    STATE_PLAYING,
)
from homeassistant.const import CONF_ATTRIBUTE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_GAMMA_CURVE,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
)
from custom_components.powercalc.errors import StrategyConfigurationError

from .strategy_interface import PowerCalculationStrategyInterface

ALLOWED_DOMAINS = [fan.DOMAIN, light.DOMAIN, media_player.DOMAIN]
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CALIBRATE): vol.All(
            cv.ensure_list,
            [vol.Match("^[0-9]+ -> ([0-9]*[.])?[0-9]+$")],
        ),
        vol.Optional(CONF_MIN_POWER): vol.Coerce(float),
        vol.Optional(CONF_MAX_POWER): vol.Coerce(float),
        vol.Optional(CONF_GAMMA_CURVE): vol.Coerce(float),
        vol.Optional(CONF_ATTRIBUTE): cv.string,
    },
)

_LOGGER = logging.getLogger(__name__)


class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: ConfigType,
        hass: HomeAssistant,
        source_entity: SourceEntity,
        standby_power: float | None,
    ) -> None:
        self._config = config
        self._hass = hass
        self._source_entity = source_entity
        self._standby_power = standby_power
        self._calibration: list[tuple[int, float]] | None = None

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate the current power consumption."""
        if self._calibration is None:
            self._calibration = self.create_calibrate_list()

        value = self.get_current_state_value(entity_state)
        if value is None:
            return None

        min_calibrate = self.get_min_calibrate(value)
        max_calibrate = self.get_max_calibrate(value)
        min_value = min_calibrate[0]
        max_value = max_calibrate[0]

        _LOGGER.debug(
            "%s: Linear mode state value: %d range(%d-%d)",
            self._source_entity.entity_id,
            value,
            min_value,
            max_value,
        )

        min_power = min_calibrate[1]
        max_power = max_calibrate[1]

        value_range = max_value - min_value
        power_range = max_power - min_power

        gamma_curve = self._config.get(CONF_GAMMA_CURVE) or 1

        relative_value = (value - min_value) / value_range

        power = power_range * relative_value**gamma_curve + min_power

        return Decimal(power)

    def get_min_calibrate(self, value: int) -> tuple[int, float]:
        """Get closest lower value from calibration table."""
        return min(self._calibration or (), key=lambda v: (v[0] > value, value - v[0]))

    def get_max_calibrate(self, value: int) -> tuple[int, float]:
        """Get closest higher value from calibration table."""
        return max(self._calibration or (), key=lambda v: (v[0] > value, value - v[0]))

    def create_calibrate_list(self) -> list[tuple[int, float]]:
        """Build a table of calibration values."""
        calibration_list: list[tuple[int, float]] = []

        calibrate = self._config.get(CONF_CALIBRATE)
        if calibrate is None or len(calibrate) == 0:
            full_range = self.get_entity_value_range()
            min_value = full_range[0]
            max_value = full_range[1]
            min_power = self._config.get(CONF_MIN_POWER) or self._standby_power or 0
            calibration_list.append((min_value, float(min_power)))
            calibration_list.append(
                (max_value, float(self._config.get(CONF_MAX_POWER))),  # type: ignore[arg-type]
            )
            return calibration_list

        for line in calibrate:
            parts = line.split(" -> ")
            calibration_list.append((int(parts[0]), float(parts[1])))

        return sorted(calibration_list, key=lambda tup: tup[0])

    def get_entity_value_range(self) -> tuple:
        """Get the min/max range for a given entity domain."""
        if self._source_entity.domain == fan.DOMAIN:
            return 0, 100

        if self._source_entity.domain == light.DOMAIN:
            return 0, 255

        if self._source_entity.domain == media_player.DOMAIN:
            return 0, 100
        raise StrategyConfigurationError(
            "Unsupported domain for linear strategy",
        )  # pragma: no cover

    def get_current_state_value(self, entity_state: State) -> int | None:
        """Get the current entity state, i.e. selected brightness."""
        attribute = self.get_attribute(entity_state)
        if attribute:
            value: int | None = entity_state.attributes.get(attribute)
            if value is None:
                _LOGGER.warning(
                    "No %s attribute for entity: %s",
                    attribute,
                    entity_state.entity_id,
                )
                return None
            if attribute == ATTR_BRIGHTNESS and value > 255:
                value = 255
            # Convert volume level to 0-100 range
            if attribute == ATTR_MEDIA_VOLUME_LEVEL:
                if entity_state.state != STATE_PLAYING:
                    return None
                if entity_state.attributes.get(ATTR_MEDIA_VOLUME_MUTED) is True:
                    value = 0
                value *= 100
            return value

        try:
            return int(float(entity_state.state))
        except ValueError:
            _LOGGER.error(
                "Expecting state to be a number for entity: %s",
                entity_state.entity_id,
            )
            return None

    def get_attribute(self, entity_state: State) -> str | None:
        """Returns the attribute which needs to be read for the linear calculation."""
        if CONF_ATTRIBUTE in self._config:
            return self._config.get(CONF_ATTRIBUTE)

        entity_domain = entity_state.domain  # type: ignore
        if entity_domain == light.DOMAIN:
            return ATTR_BRIGHTNESS

        if entity_domain == fan.DOMAIN:
            return ATTR_PERCENTAGE

        if entity_domain == media_player.DOMAIN:
            return ATTR_MEDIA_VOLUME_LEVEL

        return None

    async def validate_config(self) -> None:
        """Validate correct setup of the strategy."""
        if not self._config.get(CONF_CALIBRATE):
            if self._source_entity.domain not in ALLOWED_DOMAINS:
                raise StrategyConfigurationError(
                    "Entity domain not supported for linear mode. Must be one of: {}, or use the calibrate option".format(
                        ",".join(ALLOWED_DOMAINS),
                    ),
                    "linear_unsupported_domain",
                )
            if not self._config.get(CONF_MAX_POWER):
                raise StrategyConfigurationError(
                    "Linear strategy must have at least 'max power' or 'calibrate' defined",
                    "linear_mandatory",
                )

        min_power = self._config.get(CONF_MIN_POWER)
        max_power = self._config.get(CONF_MAX_POWER)
        if min_power and max_power and min_power >= max_power:
            raise StrategyConfigurationError(
                "Max power cannot be lower than min power",
                "linear_min_higher_as_max",
            )
