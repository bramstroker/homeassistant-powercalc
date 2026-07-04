from __future__ import annotations

from decimal import Decimal, DecimalException
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_COST_SENSOR_PRECISION,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_SENSOR,
    DEFAULT_COST_SENSOR_PRECISION,
    DOMAIN,
    DOMAIN_CONFIG,
)
from custom_components.powercalc.device_binding import get_device_info

from .abstract import (
    BaseEntity,
    bind_entity_to_area,
    bind_entity_to_device,
    generate_cost_sensor_entity_id,
    generate_cost_sensor_name,
)
from .energy import EnergySensor

COST_ICON = "mdi:cash"
ATTR_LAST_ENERGY = "last_energy"

_LOGGER = logging.getLogger(__name__)


def _parse_decimal(state: State | None) -> Decimal | None:
    """Parse a numeric state into a Decimal, returning None when it is not a usable number."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        return Decimal(state.state)
    except DecimalException, ValueError:
        return None


def create_cost_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    energy_sensor: EnergySensor,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
) -> CostSensor | None:
    """Create a cost sensor tracking the cost of the given energy sensor.

    The energy price is defined globally, either as a fixed price or a price sensor.
    When no price is configured, no cost sensor is created.
    """
    global_config: ConfigType = hass.data[DOMAIN].get(DOMAIN_CONFIG, {})
    fixed_price = global_config.get(CONF_ENERGY_PRICE)
    price_entity_id = global_config.get(CONF_ENERGY_PRICE_SENSOR)

    if fixed_price is None and not price_entity_id:
        _LOGGER.warning(
            "Cost sensor creation is enabled but no energy price is configured. "
            "Define `energy_price` or `energy_price_sensor` in the global powercalc configuration",
        )
        return None

    name_base = name if name is not None else sensor_config.get(CONF_NAME)
    cost_name = generate_cost_sensor_name(sensor_config, name_base, source_entity)
    unique_id = f"{energy_sensor.unique_id}_cost" if energy_sensor.unique_id is not None else None
    entity_id = generate_cost_sensor_entity_id(
        hass,
        sensor_config,
        source_entity,
        name=name_base,
        unique_id=unique_id,
    )

    _LOGGER.debug(
        "Creating cost sensor (entity_id=%s, source_entity=%s, fixed_price=%s, price_entity=%s)",
        entity_id,
        energy_sensor.entity_id,
        fixed_price,
        price_entity_id,
    )

    return VirtualCostSensor(
        hass=hass,
        source_energy_entity=energy_sensor.entity_id,
        entity_id=entity_id,
        unique_id=unique_id,
        name=cost_name,
        sensor_config=sensor_config,
        fixed_price=Decimal(str(fixed_price)) if fixed_price is not None else None,
        price_entity_id=price_entity_id,
        powercalc_source_entity=source_entity.entity_id if source_entity else None,
        powercalc_source_domain=source_entity.domain if source_entity else None,
        device_info=get_device_info(hass, sensor_config, source_entity),
    )


class CostSensor(BaseEntity):
    """Class which all cost sensors should extend from."""


class VirtualCostSensor(RestoreEntity, SensorEntity, CostSensor):
    """Cost sensor, accumulating the cost of the energy consumed at price-at-consumption."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_should_poll = False
    _attr_icon = COST_ICON
    _unrecorded_attributes = frozenset({ATTR_SOURCE_DOMAIN, ATTR_SOURCE_ENTITY, ATTR_LAST_ENERGY})

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
        powercalc_source_entity: str | None = None,
        powercalc_source_domain: str | None = None,
        device_info: DeviceInfo | None = None,
    ) -> None:
        self._source_energy_entity = source_energy_entity
        self._sensor_config = sensor_config
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_unit_of_measurement = hass.config.currency
        self._attr_device_info = device_info
        self._fixed_price = fixed_price
        self._price_entity_id = price_entity_id
        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self._rounding_digits = int(sensor_config.get(CONF_COST_SENSOR_PRECISION, DEFAULT_COST_SENSOR_PRECISION))
        self._attr_suggested_display_precision = self._rounding_digits
        self._state: Decimal = Decimal(0)
        self._last_energy: Decimal | None = None
        self._current_price: Decimal | None = fixed_price
        self.device_entry = async_entity_id_to_device(hass, source_energy_entity)
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        """Restore state and start tracking the source energy and price sensors."""
        if (state := await self.async_get_last_state()) is not None:
            try:
                self._state = Decimal(state.state)
            except DecimalException, ValueError:
                self._state = Decimal(0)
            last_energy = state.attributes.get(ATTR_LAST_ENERGY)
            if last_energy is not None:
                try:
                    self._last_energy = Decimal(str(last_energy))
                except DecimalException, ValueError:  # pragma: no cover
                    self._last_energy = None

        _LOGGER.debug("%s: Restoring cost sensor state: %s", self.entity_id, self._state)

        bind_entity_to_device(self.hass, self.entity_id, self.device_entry)
        bind_entity_to_area(self.hass, self.entity_id, self._sensor_config)

        # Seed the current price and, for a price sensor, track its changes so consumption
        # is always settled at the price that was in effect when it was consumed.
        if self._price_entity_id is not None:
            self._current_price = _parse_decimal(self.hass.states.get(self._price_entity_id))
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
        new_energy = _parse_decimal(event.data["new_state"])
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
            current_energy = _parse_decimal(self.hass.states.get(self._source_energy_entity))
            if current_energy is not None:
                self._accumulate(current_energy, self._current_price)

        self._current_price = _parse_decimal(event.data["new_state"])

    def _accumulate(self, new_energy: Decimal, price: Decimal | None) -> None:
        """Add the cost of the consumed energy at the given price and advance the baseline."""
        # Leave _last_energy untouched when no price is known, so the consumption is
        # priced once a price becomes available again.
        if price is None or self._last_energy is None:
            return

        delta = new_energy - self._last_energy
        # The energy sensor got reset (e.g. restart or calibrate), treat the new value as the delta.
        if delta < 0:
            delta = new_energy
        if delta == 0:
            return

        self._state += delta * price
        self._last_energy = new_energy
        self.async_write_ha_state()

    @property
    def native_value(self) -> Decimal:
        """Return the accumulated cost."""
        return Decimal(round(self._state, self._rounding_digits))

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the state attributes of the cost sensor."""
        attrs: dict[str, str] = {}
        if self._last_energy is not None:
            attrs[ATTR_LAST_ENERGY] = str(self._last_energy)

        if not self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES) and self._powercalc_source_entity:
            attrs[ATTR_SOURCE_ENTITY] = self._powercalc_source_entity
            attrs[ATTR_SOURCE_DOMAIN] = self._powercalc_source_domain or ""

        return attrs or None
