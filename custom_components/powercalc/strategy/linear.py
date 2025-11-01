from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any

from homeassistant.components import fan, lawn_mower, light, media_player, vacuum
from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    STATE_PLAYING,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_ATTRIBUTE
from homeassistant.core import HomeAssistant, State
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import TrackTemplate
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity, create_source_entity
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_GAMMA_CURVE,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.helpers import get_related_entity_by_device_class

from .strategy_interface import PowerCalculationStrategyInterface

ALLOWED_DOMAINS = [fan.DOMAIN, light.DOMAIN, media_player.DOMAIN, vacuum.DOMAIN, lawn_mower.DOMAIN]
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

ENTITY_ATTRIBUTE_MAPPING = {
    fan.DOMAIN: ATTR_PERCENTAGE,
    light.DOMAIN: ATTR_BRIGHTNESS,
    media_player.DOMAIN: ATTR_MEDIA_VOLUME_LEVEL,
}

_LOGGER = logging.getLogger(__name__)


class LinearStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        config: dict[str, Any],
        hass: HomeAssistant,
        source_entity: SourceEntity,
        standby_power: float | None,
    ) -> None:
        self._config = config
        self._hass = hass
        self._source_entity: SourceEntity = source_entity
        self._value_entity: SourceEntity | None = None
        self._attribute: str | None = None
        self._standby_power = standby_power
        self._initialized: bool = False
        self._calibration: list[tuple[int, float]] | None = None

    async def initialize(self) -> None:
        """Initialize the strategy, called once on creation."""
        self._value_entity = await self.get_value_entity()
        self._calibration = self.create_calibrate_list()

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate the current power consumption."""
        if not self._initialized:
            self._attribute = self.get_attribute(entity_state)
            self._initialized = True

        value = self.get_current_state_value(entity_state)
        if value is None:
            return None

        min_calibrate = self.get_min_calibrate(value)
        max_calibrate = self.get_max_calibrate(value)
        min_value = min_calibrate[0]
        max_value = max_calibrate[0]

        _LOGGER.debug(
            "%s: Linear mode state value: %d range(%d-%d)",
            self._value_entity.entity_id,  # type: ignore
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

    def is_enabled(self, entity_state: State) -> bool:
        """Return if this strategy is enabled based on entity state."""
        if self._source_entity.domain == media_player.DOMAIN and entity_state.state is not STATE_PLAYING:  # noqa: SIM103
            return False
        return True

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
        if isinstance(calibrate, dict):
            calibrate = [f"{key} -> {value}" for key, value in calibrate.items()]

        if calibrate is None or len(calibrate) == 0:
            full_range = self.get_entity_value_range()
            min_value = full_range[0]
            max_value = full_range[1]
            min_power = self._config.get(CONF_MIN_POWER) or self._standby_power or 0
            calibration_list.append((min_value, float(min_power)))
            calibration_list.append(
                (max_value, float(self._config.get(CONF_MAX_POWER))),  # type: ignore
            )
            return calibration_list

        for line in calibrate:
            parts = line.split(" -> ")
            calibration_list.append((int(parts[0]), float(parts[1])))

        return sorted(calibration_list, key=lambda tup: tup[0])

    def get_entity_value_range(self) -> tuple:
        """Get the min/max range for a given entity domain."""
        if self._value_entity.domain == light.DOMAIN:  # type: ignore
            return 0, 255

        return 0, 100

    def get_current_state_value(self, entity_state: State) -> int | None:
        """Get the current entity state, i.e. selected brightness."""
        if self._attribute:
            return self.get_value_from_attribute(entity_state)

        if self._value_entity.entity_id is not self._source_entity.entity_id:  # type: ignore
            # If the value entity is different from the source entity, we need to fetch the state of the value entity
            entity_state = self._hass.states.get(self._value_entity.entity_id)  # type: ignore
            if not entity_state:
                _LOGGER.error(
                    "Value entity %s not found",
                    self._value_entity.entity_id,  # type: ignore
                )
                return None

        try:
            return int(float(entity_state.state))
        except ValueError:
            _LOGGER.error(
                "Expecting state to be a number for entity: %s",
                entity_state.entity_id,
            )
            return None

    def get_value_from_attribute(self, entity_state: State) -> int | None:
        value: int | None = entity_state.attributes.get(self._attribute)  # type: ignore[arg-type]
        if value is None:
            _LOGGER.warning(
                "No %s attribute for entity: %s",
                self._attribute,
                entity_state.entity_id,
            )
            return None
        if self._attribute == ATTR_BRIGHTNESS and value > 255:
            value = 255
        # Convert volume level to 0-100 range
        if self._attribute == ATTR_MEDIA_VOLUME_LEVEL:
            if entity_state.attributes.get(ATTR_MEDIA_VOLUME_MUTED) is True:
                value = 0
            value *= 100
        return value

    def get_attribute(self, entity_state: State) -> str | None:
        """Returns the attribute which contains the value for the linear calculation."""
        if CONF_ATTRIBUTE in self._config:
            return str(self._config.get(CONF_ATTRIBUTE))

        entity_domain = entity_state.domain
        return ENTITY_ATTRIBUTE_MAPPING.get(entity_domain)

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
            if CONF_MAX_POWER not in self._config:
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

    async def get_value_entity(self) -> SourceEntity:
        """Set the value entity based on the current state."""
        if self._source_entity.domain in (vacuum.DOMAIN, lawn_mower.DOMAIN) and self._attribute is None and self._source_entity.entity_entry:
            # For vacuum cleaner and lawn mower, battery level is a separate entity
            related_entity = get_related_entity_by_device_class(
                self._hass,
                self._source_entity.entity_entry,
                SensorDeviceClass.BATTERY,
            )
            if not related_entity:
                raise StrategyConfigurationError(
                    "No battery entity found for vacuum cleaner",
                    "linear_no_battery_entity",
                )
            return await create_source_entity(related_entity, self._hass)

        return self._value_entity or self._source_entity

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        """Return entities to track for this strategy."""
        if self._value_entity and self._value_entity.entity_id != self._source_entity.entity_id:
            return [self._value_entity.entity_id]

        return []
