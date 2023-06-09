from __future__ import annotations

import logging
from decimal import Decimal

import homeassistant.helpers.entity_registry as er
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    ENERGY_KILO_WATT_HOUR,
    TIME_HOURS,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_POWER_SENSOR_ID,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    UnitPrefix,
)
from custom_components.powercalc.errors import SensorConfigurationError

from .abstract import (
    BaseEntity,
    generate_energy_sensor_entity_id,
    generate_energy_sensor_name,
)
from .power import PowerSensor, RealPowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_energy_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
    source_entity: SourceEntity,
) -> EnergySensor:
    """Create the energy sensor entity."""
    # User specified an existing energy sensor with "energy_sensor_id" option. Just return that one
    if CONF_ENERGY_SENSOR_ID in sensor_config:
        ent_reg = er.async_get(hass)
        energy_sensor_id = sensor_config[CONF_ENERGY_SENSOR_ID]
        entity_entry = ent_reg.async_get(energy_sensor_id)
        if entity_entry is None:
            raise SensorConfigurationError(
                f"No energy sensor with id {energy_sensor_id} found in your HA instance. "
                "Double check `energy_sensor_id` setting",
            )
        return RealEnergySensor(entity_entry)

    # User specified an existing power sensor with "power_sensor_id" option. Try to find a corresponding energy sensor
    if CONF_POWER_SENSOR_ID in sensor_config and isinstance(
        power_sensor,
        RealPowerSensor,
    ):
        # User can force the energy sensor creation with "force_energy_sensor_creation" option.
        # If they did, don't look for an energy sensor
        if (
            CONF_FORCE_ENERGY_SENSOR_CREATION not in sensor_config
            or not sensor_config.get(CONF_FORCE_ENERGY_SENSOR_CREATION)
        ):
            real_energy_sensor = find_related_real_energy_sensor(hass, power_sensor)
            if real_energy_sensor:
                _LOGGER.debug(
                    f"Found existing energy sensor '{real_energy_sensor.entity_id}' "
                    f"for the power sensor '{power_sensor.entity_id}'",
                )
                return real_energy_sensor
            _LOGGER.debug(
                f"No existing energy sensor found for the power sensor '{power_sensor.entity_id}'",
            )
        else:
            _LOGGER.debug(
                f"Forced energy sensor generation for the power sensor '{power_sensor.entity_id}'",
            )

    # Create an energy sensor based on riemann integral integration, which uses the virtual powercalc sensor as source.
    name = generate_energy_sensor_name(
        sensor_config,
        sensor_config.get(CONF_NAME),
        source_entity,
    )
    unique_id = None
    if power_sensor.unique_id:
        unique_id = f"{power_sensor.unique_id}_energy"

    entity_id = generate_energy_sensor_entity_id(
        hass,
        sensor_config,
        source_entity,
        unique_id=unique_id,
    )
    entity_category = sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY)

    unit_prefix = get_unit_prefix(hass, sensor_config, power_sensor)

    _LOGGER.debug("Creating energy sensor: %s", name)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        entity_category=entity_category,
        name=name,
        round_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),  # type: ignore
        unit_prefix=unit_prefix,
        unit_time=TIME_HOURS,  # type: ignore
        integration_method=sensor_config.get(CONF_ENERGY_INTEGRATION_METHOD)
        or DEFAULT_ENERGY_INTEGRATION_METHOD,
        powercalc_source_entity=source_entity.entity_id,
        powercalc_source_domain=source_entity.domain,
        sensor_config=sensor_config,
    )


def get_unit_prefix(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    power_sensor: PowerSensor,
) -> str | None:
    unit_prefix = sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX)

    power_unit = power_sensor.unit_of_measurement
    power_state = hass.states.get(power_sensor.entity_id)
    if power_unit is None and power_state:
        power_unit = power_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

    # When the power sensor is in kW, we don't want to add an extra k prefix.
    # As this would result in an energy sensor having kkWh unit, which is obviously invalid
    if power_unit == UnitOfPower.KILO_WATT and unit_prefix == UnitPrefix.KILO:
        unit_prefix = UnitPrefix.NONE

    if unit_prefix == UnitPrefix.NONE:
        unit_prefix = None
    return unit_prefix


@callback
def find_related_real_energy_sensor(
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
        if entry.device_class == SensorDeviceClass.ENERGY
        or entry.unit_of_measurement == ENERGY_KILO_WATT_HOUR
    ]
    if not energy_sensors:
        return None

    return RealEnergySensor(energy_sensors[0])


class EnergySensor(BaseEntity):
    """Class which all energy sensors should extend from."""


class VirtualEnergySensor(IntegrationSensor, EnergySensor):
    """Virtual energy sensor, totalling kWh."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        source_entity: str,
        unique_id: str | None,
        entity_id: str,
        entity_category: EntityCategory | None,
        name: str | None,
        round_digits: int,
        unit_prefix: str | None,
        unit_time: UnitOfTime,
        integration_method: str,
        powercalc_source_entity: str,
        powercalc_source_domain: str,
        sensor_config: ConfigType,
    ) -> None:
        super().__init__(
            source_entity=source_entity,
            name=name,
            round_digits=round_digits,
            unit_prefix=unit_prefix,
            unit_time=unit_time,
            integration_method=integration_method,
            unique_id=unique_id,
        )

        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self._sensor_config = sensor_config
        self.entity_id = entity_id
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the state attributes of the energy sensor."""
        if self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            return super().extra_state_attributes

        attrs = {
            ATTR_SOURCE_ENTITY: self._powercalc_source_entity,
            ATTR_SOURCE_DOMAIN: self._powercalc_source_domain,
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
        _LOGGER.debug(f"{self.entity_id}: Reset energy sensor")
        self._state = 0
        self.async_write_ha_state()

    async def async_calibrate(self, value: str) -> None:
        _LOGGER.debug(f"{self.entity_id}: Calibrate energy sensor to: {value}")
        self._state = Decimal(value)
        self.async_write_ha_state()


class RealEnergySensor(EnergySensor):
    """Contains a reference to an existing energy sensor entity."""

    def __init__(self, entity_entry: er.RegistryEntry) -> None:
        self._entity_entry = entity_entry
        self.entity_id = self._entity_entry.entity_id

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._entity_entry.name or self._entity_entry.original_name

    @property
    def unique_id(self) -> str | None:
        """Return the unique_id of the sensor."""
        return self._entity_entry.unique_id
