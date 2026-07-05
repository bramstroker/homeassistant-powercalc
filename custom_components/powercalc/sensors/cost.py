from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import ATTR_LAST_RESET, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_UNIQUE_ID,
    UnitOfEnergy,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_COST,
    CONF_COST_SENSOR_PRECISION,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_MULTIPLIER,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_PRICE_SURCHARGE,
    CONF_ENERGY_SENSOR_ID,
    DEFAULT_COST_SENSOR_PRECISION,
    DOMAIN,
    DOMAIN_CONFIG,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.unit import convert_to_decimal, parse_decimal

from .abstract import (
    BaseEntity,
    generate_cost_sensor_entity_id,
    generate_cost_sensor_name,
)
from .energy import EnergySensor, RealEnergySensor

if TYPE_CHECKING:
    from datetime import datetime

    from .utility_meter import VirtualUtilityMeter

COST_ICON = "mdi:cash"
ATTR_LAST_ENERGY = "last_energy"

_LOGGER = logging.getLogger(__name__)


def _parse_scaled(state: State | None, unit_to_factor: Callable[[str | None], Decimal]) -> Decimal | None:
    """Parse a numeric state into a Decimal, scaled by a factor derived from its unit.

    Both energy amounts (converted to kWh) and prices (converted to per kWh) are parsed this
    way; ``unit_to_factor`` maps the state's unit of measurement to the multiplier to apply.
    """
    value = parse_decimal(state)
    if value is None:
        return None
    assert state is not None  # a parsed value implies the state is present and numeric
    return value * unit_to_factor(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))


def _to_kwh_factor(unit: str | None) -> Decimal:
    """Return the multiplier to convert an energy value expressed in `unit` to kWh.

    Falls back to 1 (assume kWh) when the unit is missing or not a recognizable energy unit.
    """
    if not unit or unit == UnitOfEnergy.KILO_WATT_HOUR:
        return Decimal(1)
    if (factor := convert_to_decimal(1, unit, UnitOfEnergy.KILO_WATT_HOUR)) is not None:
        return factor
    _LOGGER.warning("Cannot convert energy unit '%s' to kWh, assuming kWh", unit)
    return Decimal(1)


def _price_per_kwh_factor(unit: str | None) -> Decimal:
    """Return the multiplier that converts a price value to a price per kWh.

    Price sensors express their unit as ``<currency>/<energy>`` (for example ``EUR/MWh``).
    The energy denominator determines how the raw value maps to a per-kWh price, e.g.
    ``EUR/MWh`` -> value * 0.001 and ``EUR/Wh`` -> value * 1000. Falls back to 1 (assume the
    value is already per kWh) when there is no denominator or it is not a recognizable unit.
    """
    if not unit or "/" not in unit:
        return Decimal(1)
    denominator = unit.rsplit("/", 1)[-1].strip()
    if not denominator or denominator == UnitOfEnergy.KILO_WATT_HOUR:
        return Decimal(1)
    if (factor := convert_to_decimal(1, UnitOfEnergy.KILO_WATT_HOUR, denominator)) is not None:
        return factor
    _LOGGER.warning("Cannot convert energy price unit '%s' to a per-kWh price, assuming per kWh", unit)
    return Decimal(1)


def _currency_from_price_unit(unit: str | None) -> str | None:
    """Derive the monetary unit from an energy price sensor's unit of measurement.

    Price sensors typically express their unit as ``<currency>/kWh`` (for example
    ``EUR/kWh`` or ``€/kWh``). The part before the slash is the currency the cost is
    denominated in. Returns None when no currency can be determined.
    """
    if not unit:
        return None
    currency = unit.split("/", 1)[0].strip()
    return currency or None


def create_cost_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    energy_sensor: EnergySensor | VirtualUtilityMeter,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
    reset_on_source_reset: bool = False,
    unique_id: str | None = None,
) -> CostSensor | None:
    """Create a cost sensor tracking the cost of the given energy sensor.

    The energy sensor can be a regular energy sensor or a utility meter. The energy
    price is defined globally, either as a fixed price or a price sensor. When no price
    is configured, no cost sensor is created. A ``unique_id`` can be provided to override
    the id derived from the energy sensor (used for standalone cost sensor config entries).
    """
    global_config: ConfigType = hass.data[DOMAIN].get(DOMAIN_CONFIG, {})
    fixed_price = global_config.get(CONF_ENERGY_PRICE)
    price_entity_id = global_config.get(CONF_ENERGY_PRICE_SENSOR)
    price_surcharge = Decimal(str(global_config.get(CONF_ENERGY_PRICE_SURCHARGE, 0) or 0))
    price_multiplier = Decimal(str(global_config.get(CONF_ENERGY_PRICE_MULTIPLIER, 1) or 1))

    if fixed_price is None and not price_entity_id:
        _LOGGER.warning(
            "Cost sensor creation is enabled but no energy price is configured. "
            "Define `energy_price` or `energy_price_sensor` in the global powercalc configuration",
        )
        return None

    name_base = name if name is not None else sensor_config.get(CONF_NAME)
    cost_name = generate_cost_sensor_name(sensor_config, name_base, source_entity)
    if unique_id is None and energy_sensor.unique_id is not None:
        unique_id = f"{energy_sensor.unique_id}_cost"
    entity_id = generate_cost_sensor_entity_id(
        hass,
        sensor_config,
        source_entity,
        name=name_base,
        unique_id=unique_id,
    )

    _LOGGER.debug(
        (
            "Creating cost sensor (entity_id=%s, source_entity=%s, fixed_price=%s, "
            "price_entity=%s, price_surcharge=%s, price_multiplier=%s)"
        ),
        entity_id,
        energy_sensor.entity_id,
        fixed_price,
        price_entity_id,
        price_surcharge,
        price_multiplier,
    )

    return CostSensor(
        hass=hass,
        source_energy_entity=energy_sensor.entity_id,
        entity_id=entity_id,
        unique_id=unique_id,
        name=cost_name,
        sensor_config=sensor_config,
        fixed_price=Decimal(str(fixed_price)) if fixed_price is not None else None,
        price_entity_id=price_entity_id,
        price_surcharge=price_surcharge,
        price_multiplier=price_multiplier,
        reset_on_source_reset=reset_on_source_reset,
    )


def create_cost_sensor_for_energy_entity(hass: HomeAssistant, sensor_config: ConfigType) -> CostSensor | None:
    """Create a standalone cost sensor tracking an existing (non-powercalc) energy sensor.

    The tracked energy sensor is read from the ``cost`` block (YAML) or the flat
    ``energy_sensor_id`` key (GUI config entry).
    """
    cost_config = sensor_config.get(CONF_COST, {})
    energy_sensor_id = cost_config.get(CONF_ENERGY_SENSOR_ID) or sensor_config[CONF_ENERGY_SENSOR_ID]
    entity_entry = er.async_get(hass).async_get(energy_sensor_id)
    if entity_entry is None:
        raise SensorConfigurationError(
            f"No energy sensor with id {energy_sensor_id} found in your HA instance. "
            "Double check the `energy_sensor_id` setting",
        )
    energy_sensor = RealEnergySensor(
        entity_entry.entity_id,
        entity_entry.name or entity_entry.original_name,
        entity_entry.unique_id,
    )
    # In YAML the name is optional, fall back to the name of the tracked energy sensor.
    name = sensor_config.get(CONF_NAME) or energy_sensor.name
    return create_cost_sensor(
        hass,
        sensor_config,
        energy_sensor,
        name=name,
        unique_id=sensor_config.get(CONF_UNIQUE_ID),
    )


class CostSensor(BaseEntity, RestoreEntity, SensorEntity):
    """Cost sensor, accumulating the cost of the energy consumed at price-at-consumption."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_should_poll = False
    _attr_icon = COST_ICON
    _unrecorded_attributes = frozenset({ATTR_LAST_ENERGY})

    def __init__(
        self,
        hass: HomeAssistant,
        source_energy_entity: str,
        entity_id: str,
        sensor_config: ConfigType,
        name: str | None = None,
        unique_id: str | None = None,
        fixed_price: Decimal | None = None,
        price_entity_id: str | None = None,
        price_surcharge: Decimal = Decimal(0),
        price_multiplier: Decimal = Decimal(1),
        reset_on_source_reset: bool = False,
    ) -> None:
        self._source_energy_entity = source_energy_entity
        self._sensor_config = sensor_config
        self._reset_on_source_reset = reset_on_source_reset
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_unit_of_measurement = hass.config.currency
        self._fixed_price = fixed_price
        self._price_entity_id = price_entity_id
        self._price_surcharge = price_surcharge
        self._price_multiplier = price_multiplier
        self._rounding_digits = int(sensor_config.get(CONF_COST_SENSOR_PRECISION, DEFAULT_COST_SENSOR_PRECISION))
        self._attr_suggested_display_precision = self._rounding_digits
        self._state: Decimal = Decimal(0)
        self._last_energy: Decimal | None = None
        self._current_price: Decimal | None = self._effective_price(fixed_price)
        # Only a resetting (per utility meter cycle) sensor uses last_reset; a lifetime cost
        # sensor accumulates monotonically and leaves it None.
        self._attr_last_reset: datetime | None = None
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        """Restore state and start tracking the source energy and price sensors."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            self._state = parse_decimal(state) or Decimal(0)
            self._last_energy = parse_decimal(state.attributes.get(ATTR_LAST_ENERGY))

        # A resetting (per utility meter cycle) cost sensor exposes last_reset so long-term
        # statistics treat each cycle reset as a new cycle rather than negative consumption.
        # Restore it across restarts, falling back to now for a freshly created sensor.
        if self._reset_on_source_reset:
            restored = dt_util.parse_datetime(state.attributes.get(ATTR_LAST_RESET, "")) if state else None
            self._attr_last_reset = restored or dt_util.utcnow()

        _LOGGER.debug("%s: Restoring cost sensor state: %s", self.entity_id, self._state)

        # Seed the current price and, for a price sensor, track its changes so consumption
        # is always settled at the price that was in effect when it was consumed.
        if self._price_entity_id is not None:
            price_state = self.hass.states.get(self._price_entity_id)
            # Prefer the currency of the price sensor (e.g. `€/kWh` -> `€`) over the HA currency.
            price_unit = price_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if price_state else None
            if (currency := _currency_from_price_unit(price_unit)) is not None:
                self._attr_native_unit_of_measurement = currency
            self._current_price = self._effective_price(_parse_scaled(price_state, _price_per_kwh_factor))
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._price_entity_id],
                    self._handle_price_state_change,
                ),
            )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._source_energy_entity],
                self._handle_energy_state_change,
            ),
        )

    @callback
    def _handle_energy_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Accumulate cost based on the delta of the energy sensor and the current price."""
        new_energy = _parse_scaled(event.data["new_state"], _to_kwh_factor)
        if new_energy is None:
            return

        # First reading only establishes a baseline to measure deltas from.
        if self._last_energy is None:
            self._last_energy = new_energy
            return

        self._accumulate(new_energy, self._current_price)

    @callback
    def _handle_price_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Settle the energy consumed so far at the previous price, then adopt the new price."""
        # Recalculate the outstanding energy delta with the previously known price before switching.
        if self._last_energy is not None and self._current_price is not None:
            current_energy = _parse_scaled(self.hass.states.get(self._source_energy_entity), _to_kwh_factor)
            if current_energy is not None:
                self._accumulate(current_energy, self._current_price)

        self._current_price = self._effective_price(_parse_scaled(event.data["new_state"], _price_per_kwh_factor))

    def _effective_price(self, price: Decimal | None) -> Decimal | None:
        if price is None:
            return None
        return (price + self._price_surcharge) * self._price_multiplier

    def _accumulate(self, new_energy: Decimal, price: Decimal | None) -> None:
        """Add the cost of the consumed energy at the given price and advance the baseline."""
        # Leave _last_energy untouched when no price is known, so the consumption is
        # priced once a price becomes available again.
        if price is None or self._last_energy is None:
            return

        delta = new_energy - self._last_energy
        if delta < 0:
            if self._reset_on_source_reset:
                # The source (utility meter) reset for a new cycle, start the cost cycle over.
                self._state = Decimal(0)
                self._last_energy = new_energy
                self._attr_last_reset = dt_util.utcnow()
                self.async_write_ha_state()
                return
            # The energy sensor got reset (e.g. restart or calibrate), treat the new value as the delta.
            delta = new_energy
        if delta == 0:
            return

        self._state += delta * price
        self._last_energy = new_energy
        self.async_write_ha_state()

    @callback
    def async_reset(self) -> None:
        """Reset the cost sensor to zero from the current source energy reading."""
        _LOGGER.debug("%s: Reset cost sensor", self.entity_id)
        self._state = Decimal(0)
        self._attr_last_reset = dt_util.utcnow()
        self._set_current_energy_baseline()
        self.async_write_ha_state()

    async def async_calibrate(self, value: str) -> None:
        """Set the cost sensor to the given value from the current source energy reading."""
        _LOGGER.debug("%s: Calibrate cost sensor to: %s", self.entity_id, value)
        self._state = Decimal(value)
        self._set_current_energy_baseline()
        self.async_write_ha_state()

    def _set_current_energy_baseline(self) -> None:
        current_energy = _parse_scaled(self.hass.states.get(self._source_energy_entity), _to_kwh_factor)
        if current_energy is not None:
            self._last_energy = current_energy

    @property
    def native_value(self) -> Decimal:
        """Return the accumulated cost."""
        return Decimal(round(self._state, self._rounding_digits))

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the state attributes of the cost sensor."""
        if self._last_energy is None:
            return None
        return {ATTR_LAST_ENERGY: str(self._last_energy)}
