from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import math

from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, State
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import TrackTemplate
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from custom_components.powercalc.const import CONF_BASE_POWER, CONF_ENERGY_PER_PERCENT, CONF_MAX_POWER, CONF_WINDOW
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.validation import vol

from .strategy_interface import PowerCalculationStrategyInterface

DEFAULT_WINDOW = 600


def finite_number(value: float) -> float:
    if not math.isfinite(value):
        raise vol.Invalid("Expected a finite number")
    return value


def validate_config_values(config: ConfigType) -> ConfigType:
    if CONF_MAX_POWER in config and config[CONF_MAX_POWER] < config[CONF_BASE_POWER]:
        raise vol.Invalid("max_power must be at least base_power")
    try:
        window = timedelta(seconds=config[CONF_WINDOW])
    except OverflowError as err:
        raise vol.Invalid("window is too large") from err
    if window <= timedelta(0):
        raise vol.Invalid("window must be at least one microsecond")
    return config


CONFIG_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(CONF_ENTITY_ID): cv.entity_id,
            vol.Required(CONF_ENERGY_PER_PERCENT): vol.All(
                vol.Coerce(float), finite_number, vol.Range(min=0, min_included=False)
            ),
            vol.Optional(CONF_BASE_POWER, default=0): vol.All(vol.Coerce(float), finite_number, vol.Range(min=0)),
            vol.Optional(CONF_WINDOW, default=DEFAULT_WINDOW): vol.All(
                vol.Coerce(float), finite_number, vol.Range(min=0, min_included=False)
            ),
            vol.Optional(CONF_MAX_POWER): vol.All(vol.Coerce(float), finite_number, vol.Range(min=0)),
        },
    ),
    validate_config_values,
)


@dataclass
class BatterySample:
    timestamp: datetime
    percentage: Decimal


class BatteryRateStrategy(PowerCalculationStrategyInterface):
    def __init__(self, hass: HomeAssistant, config: ConfigType) -> None:
        self._hass = hass
        try:
            config = CONFIG_SCHEMA(config)
        except vol.Invalid as err:
            raise StrategyConfigurationError(f"Invalid battery_rate configuration: {err}") from err
        self._entity_id: str = config[CONF_ENTITY_ID]
        self._window = timedelta(seconds=config[CONF_WINDOW])
        self._energy_per_percent = Decimal(str(config[CONF_ENERGY_PER_PERCENT]))
        self._base_power = Decimal(str(config[CONF_BASE_POWER]))
        self._max_power = Decimal(str(config[CONF_MAX_POWER])) if CONF_MAX_POWER in config else None
        self._samples: list[BatterySample] = []
        self._last_valid_reading_at: datetime | None = None
        self._has_invalid_reading = False

    async def async_update_state(self) -> None:
        state = self._hass.states.get(self._entity_id)
        percentage = None
        if state is not None:
            with suppress(InvalidOperation):
                percentage = Decimal(state.state)
        self.record_reading(dt_util.utcnow(), percentage)

    async def calculate(self, entity_state: State) -> Decimal | None:
        return self.calculate_power(dt_util.utcnow())

    def get_entities_to_track(self) -> list[str | TrackTemplate]:
        return [self._entity_id]

    def get_update_interval(self) -> timedelta:
        return min(timedelta(seconds=60), self._window)

    def get_next_update_time(self) -> datetime | None:
        if len(self._samples) > 1:
            return self._samples[1].timestamp + self._window
        return None

    def record_reading(self, now: datetime, percentage: Decimal | None) -> None:
        """Retain recent history across short invalid gaps, without bridging a discharge."""
        if percentage is None or not percentage.is_finite() or not 0 <= percentage <= 100:
            self._has_invalid_reading = True
            if self._last_valid_reading_at is not None and now - self._last_valid_reading_at >= self._window:
                self._samples.clear()
            self._prune_samples(now)
            return

        if self._last_valid_reading_at is not None:
            gap = now - self._last_valid_reading_at
            has_long_invalid_gap = self._has_invalid_reading and gap >= self._window
            dropped_across_gap = (
                self._has_invalid_reading and bool(self._samples) and percentage < self._samples[-1].percentage
            )
            if gap < timedelta(0) or has_long_invalid_gap or dropped_across_gap:
                self._samples.clear()
        self._last_valid_reading_at = now
        self._has_invalid_reading = False
        sample = BatterySample(now, percentage)
        if self._samples and now == self._samples[-1].timestamp:
            self._samples[-1] = sample
        elif not self._samples or percentage != self._samples[-1].percentage:
            self._samples.append(sample)
        self._prune_samples(now)

    def calculate_power(self, now: datetime) -> Decimal | None:
        """Use step-held percentages and a full window denominator, including during warmup."""
        if not self._samples:
            return None
        self._prune_samples(now)
        lowest_percentage = min(sample.percentage for sample in self._samples)
        gained = self._samples[-1].percentage - lowest_percentage
        rate = gained * Decimal(3600) / Decimal(str(self._window.total_seconds()))
        power = self._base_power + rate * self._energy_per_percent
        return min(power, self._max_power) if self._max_power is not None else power

    def _prune_samples(self, now: datetime) -> None:
        # Keep the last sample at or before the cutoff to carry its value forward.
        while len(self._samples) > 1 and now - self._samples[1].timestamp >= self._window:
            self._samples.pop(0)
