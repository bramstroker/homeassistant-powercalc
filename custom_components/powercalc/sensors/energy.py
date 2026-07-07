from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import inspect
import logging
from typing import Any

from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.entity import EntityCategory
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_FILTER_OUTLIER_MAX,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_POWER_SENSOR_ID,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENERGY_UPDATE_INTERVAL,
    UnitPrefix,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.filter.outlier import OutlierFilter

from .abstract import (
    BaseEntity,
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
)
from .power import PowerSensor, RealPowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


def _numeric_state_value(state: State | None) -> float | None:
    """Return the numeric value of a state, or None when it is not a usable number."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        return float(state.state)
    except TypeError, ValueError:
        return None


def create_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
    source_entity: SourceEntity | None = None,
) -> EnergySensor:
    """Create the energy sensor entity."""

    # Check for existing energy sensor
    energy_sensor = _get_existing_energy_sensor(hass, sensor_config)
    if energy_sensor:
        return energy_sensor

    # Check if we should find or create a related energy sensor
    energy_sensor = _get_related_energy_sensor(hass, sensor_config, power_sensor)
    if energy_sensor:
        return energy_sensor

    # Create a new virtual energy sensor based on the virtual power sensor
    return _create_virtual_energy_sensor(hass, sensor_config, power_sensor, source_entity)


def resolve_existing_energy_sensor(hass: HomeAssistant, energy_sensor_id: str) -> RealEnergySensor:
    """Look up an existing energy sensor in the entity registry, raising when not found."""
    entity_entry = er.async_get(hass).async_get(energy_sensor_id)
    if entity_entry is None:
        raise SensorConfigurationError(
            f"No energy sensor with id {energy_sensor_id} found in your HA instance. "
            "Double check the `energy_sensor_id` setting",
        )
    return RealEnergySensor.from_registry_entry(entity_entry)


def _get_existing_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
) -> EnergySensor | None:
    """Check if the user specified an existing energy sensor."""
    if CONF_ENERGY_SENSOR_ID not in sensor_config:
        return None

    return resolve_existing_energy_sensor(hass, sensor_config[CONF_ENERGY_SENSOR_ID])


def _get_related_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
) -> EnergySensor | None:
    """Find or create a related energy sensor based on the power sensor."""

    if CONF_POWER_SENSOR_ID not in sensor_config or not isinstance(power_sensor, RealPowerSensor):
        return None

    if sensor_config.get(CONF_FORCE_ENERGY_SENSOR_CREATION):
        _LOGGER.debug(
            "Forced energy sensor generation for the power sensor '%s'",
            power_sensor.entity_id,
        )
        return None

    real_energy_sensor = _find_related_real_energy_sensor(hass, power_sensor)
    if real_energy_sensor:
        _LOGGER.debug(
            "Found existing energy sensor '%s' for the power sensor '%s'",
            real_energy_sensor.entity_id,
            power_sensor.entity_id,
        )
        return real_energy_sensor

    _LOGGER.debug(
        "No existing energy sensor found for the power sensor '%s'",
        power_sensor.entity_id,
    )
    return None


def _create_virtual_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
    source_entity: SourceEntity | None,
) -> VirtualEnergySensor:
    """Create a virtual energy sensor using riemann integral integration."""
    name = generate_energy_sensor_name(
        sensor_config,
        sensor_config.get(CONF_NAME),
        source_entity,
    )
    unique_id = f"{power_sensor.unique_id}_energy" if power_sensor.unique_id is not None else None
    entity_id = generate_energy_sensor_entity_id(
        hass,
        sensor_config,
        source_entity,
        unique_id=unique_id,
    )
    entity_category = sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY)
    unit_prefix = get_unit_prefix(hass, sensor_config, power_sensor)

    _LOGGER.debug(
        "Creating energy sensor (entity_id=%s, source_entity=%s, unit_prefix=%s)",
        entity_id,
        power_sensor.entity_id,
        unit_prefix,
    )

    return VirtualEnergySensor(
        hass=hass,
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        entity_category=entity_category,
        name=name,
        unit_prefix=unit_prefix,
        powercalc_source_entity=source_entity.entity_id if source_entity else None,
        powercalc_source_domain=source_entity.domain if source_entity else None,
        sensor_config=sensor_config,
    )


def get_unit_prefix(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
) -> str | None:
    unit_prefix = sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX)

    try:
        power_unit: UnitOfPower | str | None = (
            UnitOfPower(power_sensor.unit_of_measurement) if power_sensor.unit_of_measurement else None
        )
    except ValueError:
        power_unit = None
    power_state = hass.states.get(power_sensor.entity_id)
    if power_unit is None and power_state:
        power_unit = power_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)  # pragma: no cover

    # When the power sensor is in kW, we don't want to add an extra k prefix.
    # As this would result in an energy sensor having kkWh unit, which is obviously invalid
    if power_unit == UnitOfPower.KILO_WATT and unit_prefix == UnitPrefix.KILO:
        unit_prefix = UnitPrefix.NONE

    if unit_prefix == UnitPrefix.NONE:
        unit_prefix = None
    return unit_prefix


@callback
def _find_related_real_energy_sensor(
    hass: HomeAssistant,
    power_sensor: RealPowerSensor,
) -> RealEnergySensor | None:
    """See if a corresponding energy sensor exists in the HA installation for the power sensor."""
    if not power_sensor.device_id:
        return None

    ent_reg = er.async_get(hass)
    energy_sensors = [
        entry
        for entry in er.async_entries_for_device(
            ent_reg,
            device_id=power_sensor.device_id,
        )
        if entry.device_class == SensorDeviceClass.ENERGY or entry.unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    ]
    if not energy_sensors:
        return None

    return RealEnergySensor.from_registry_entry(energy_sensors[0])


class EnergySensor(BaseEntity):
    """Class which all energy sensors should extend from."""


class VirtualEnergySensor(IntegrationSensor, EnergySensor):
    """Virtual energy sensor, totalling kWh."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _unrecorded_attributes = frozenset({ATTR_SOURCE_DOMAIN, ATTR_SOURCE_ENTITY})

    def __init__(
        self,
        hass: HomeAssistant,
        source_entity: str,
        entity_id: str,
        sensor_config: ConfigType,
        powercalc_source_entity: str | None = None,
        powercalc_source_domain: str | None = None,
        unique_id: str | None = None,
        entity_category: EntityCategory | None = None,
        name: str | None = None,
        unit_prefix: str | None = None,
    ) -> None:
        round_digits: int = int(sensor_config.get(CONF_ENERGY_SENSOR_PRECISION, DEFAULT_ENERGY_SENSOR_PRECISION))
        integration_method: str = sensor_config.get(CONF_ENERGY_INTEGRATION_METHOD, DEFAULT_ENERGY_INTEGRATION_METHOD)

        params = {
            "hass": hass,
            "source_entity": source_entity,
            "name": name,
            "round_digits": round_digits,
            "unit_prefix": unit_prefix,
            "unit_time": UnitOfTime.HOURS,
            "integration_method": integration_method,
            "unique_id": unique_id,
            "max_sub_interval": timedelta(
                seconds=sensor_config.get(CONF_ENERGY_UPDATE_INTERVAL, DEFAULT_ENERGY_UPDATE_INTERVAL),
            ),
        }

        signature = inspect.signature(IntegrationSensor.__init__)

        params = {key: val for key, val in params.items() if key in signature.parameters}

        super().__init__(**params)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self._sensor_config = sensor_config
        self.entity_id = entity_id
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_suggested_display_precision = round_digits
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)
        self._filter_outliers = bool(sensor_config.get(CONF_ENERGY_FILTER_OUTLIER_ENABLED, False))
        self._outlier_filter = OutlierFilter(
            window_size=30,
            min_samples=5,
            max_z_score=3.5,
            max_expected_step=sensor_config.get(CONF_ENERGY_FILTER_OUTLIER_MAX, 1000),
        )
        self._last_accepted_value: float | None = None
        self._last_rejected_value: float | None = None

    def _integrate_on_state_change(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Override to add outlier filtering.

        Simply skipping integration when an outlier arrives as the ``new_state`` is not
        enough: the energy sensor integrates over consecutive states, and depending on the
        integration method the outlier also contributes when it is the *old* state of the
        following event. With the default ``left`` Riemann method the contribution of a
        state change is ``old_state * elapsed_time``, so a rejected spike still leaks into
        the total on the next update. Instead of skipping, we substitute any outlier reading
        with the last accepted value wherever it appears (as old and as new state), so it can
        never affect the energy total regardless of the integration method.
        """
        if not self._filter_outliers:
            super()._integrate_on_state_change(*args, **kwargs)
            return

        arg_list = list(args)
        state_positions = [index for index, value in enumerate(arg_list) if isinstance(value, State)]

        # The integration sensor passes the states positionally (old_state, new_state being
        # the last two). Sanitize old_state first, then new_state, since processing new_state
        # updates the tracking used to detect the outlier as a subsequent old_state.
        if len(state_positions) >= 2:
            old_index = state_positions[-2]
            arg_list[old_index] = self._replace_outlier_state(arg_list[old_index])
        if state_positions:
            new_index = state_positions[-1]
            arg_list[new_index] = self._sanitize_new_state(arg_list[new_index])

        super()._integrate_on_state_change(*arg_list, **kwargs)

    def _schedule_max_sub_interval_exceeded_if_state_is_numeric(self, source_state: State | None) -> None:
        """Prevent a rejected outlier from being integrated as the assumed constant value.

        When ``max_sub_interval`` is configured (always the case for powercalc energy sensors)
        the integration sensor keeps integrating the last known source state until a new state
        change arrives. Substitute the outlier with the last accepted value so this fallback
        does not leak the spike either.
        """
        if self._filter_outliers:
            source_state = self._replace_outlier_state(source_state)
        super()._schedule_max_sub_interval_exceeded_if_state_is_numeric(source_state)

    def _sanitize_new_state(self, state: State | None) -> State | None:
        """Feed a new state through the outlier filter, substituting rejected outliers."""
        value = _numeric_state_value(state)
        if value is None:
            return state

        if self._outlier_filter.accept(value):
            self._last_accepted_value = value
            self._last_rejected_value = None
            return state

        self._last_rejected_value = value
        _LOGGER.debug(
            "%s: Rejecting power value %s as outlier for energy integration",
            self.entity_id,
            state.state if state else value,
        )
        return self._replace_outlier_state(state)

    def _replace_outlier_state(self, state: State | None) -> State | None:
        """Replace a state holding the last rejected outlier value with the last accepted value."""
        if state is None or self._last_rejected_value is None or self._last_accepted_value is None:
            return state
        if _numeric_state_value(state) != self._last_rejected_value:
            return state
        return State(
            state.entity_id,
            str(self._last_accepted_value),
            state.attributes,
            last_changed=state.last_changed,
            last_reported=state.last_reported,
            last_updated=state.last_updated,
            context=state.context,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the state attributes of the energy sensor."""
        if self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            return super().extra_state_attributes

        if self._powercalc_source_entity is None:
            return None

        attrs = {
            ATTR_SOURCE_ENTITY: self._powercalc_source_entity or "",
            ATTR_SOURCE_DOMAIN: self._powercalc_source_domain or "",
        }
        super_attrs = super().extra_state_attributes
        if super_attrs:
            attrs.update(super_attrs)
        return attrs

    @property
    def icon(self) -> str:
        return ENERGY_ICON

    @callback
    def async_reset(self) -> None:
        _LOGGER.debug("%s: Reset energy sensor", self.entity_id)
        self._state = Decimal(0)
        self.async_write_ha_state()

    async def async_calibrate(self, value: str) -> None:
        _LOGGER.debug("%s: Calibrate energy sensor to: %s", self.entity_id, value)
        self._state = Decimal(value)
        self.async_write_ha_state()


class RealEnergySensor(EnergySensor):
    """Contains a reference to an existing energy sensor entity."""

    def __init__(
        self,
        entity_id: str,
        name: str | None = None,
        unique_id: str | None = None,
    ) -> None:
        self.entity_id = entity_id
        self._name = name
        self._unique_id = unique_id

    @classmethod
    def from_registry_entry(cls, entry: er.RegistryEntry) -> RealEnergySensor:
        """Create a reference to an existing energy sensor from its registry entry."""
        return cls(entry.entity_id, entry.name or entry.original_name, entry.unique_id)

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str | None:
        """Return the unique_id of the sensor."""
        return self._unique_id
