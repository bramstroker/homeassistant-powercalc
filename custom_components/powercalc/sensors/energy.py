from __future__ import annotations

import logging
from typing import Any, MutableMapping, Optional

import homeassistant.helpers.entity_registry as er
import homeassistant.util.dt as dt_util
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME, ENERGY_KILO_WATT_HOUR, TIME_HOURS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from ..common import SourceEntity
from ..const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_POWER_SENSOR_ID,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    UnitPrefix,
)
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
    sensor_config: dict,
    power_sensor: PowerSensor,
    source_entity: SourceEntity,
) -> EnergySensor:
    """Create the energy sensor entity"""

    # User specified an existing energy sensor with "energy_sensor_id" option. Just return that one
    if CONF_ENERGY_SENSOR_ID in sensor_config:
        ent_reg = er.async_get(hass)
        entity_entry = ent_reg.async_get(sensor_config[CONF_ENERGY_SENSOR_ID])
        return RealEnergySensor(entity_entry)

    # User specified an existing power sensor with "power_sensor_id" option. Try to find a corresponding energy sensor
    if CONF_POWER_SENSOR_ID in sensor_config and isinstance(
        power_sensor, RealPowerSensor
    ):
        real_energy_sensor = find_related_real_energy_sensor(hass, power_sensor)
        if real_energy_sensor:
            _LOGGER.debug(
                f"Found existing energy sensor '{real_energy_sensor.entity_id}' for the power sensor '{power_sensor.entity_id}'"
            )
            return real_energy_sensor

        _LOGGER.debug(
            f"No existing energy sensor found for the power sensor '{power_sensor.entity_id}'"
        )

    # Create an energy sensor based on riemann integral integration, which uses the virtual powercalc sensor as source.
    name = generate_energy_sensor_name(
        sensor_config, sensor_config.get(CONF_NAME), source_entity
    )
    unique_id = None
    if power_sensor.unique_id:
        unique_id = f"{power_sensor.unique_id}_energy"

    entity_id = generate_energy_sensor_entity_id(
        hass, sensor_config, source_entity, unique_id=unique_id
    )
    entity_category = sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY)

    unit_prefix = sensor_config.get(CONF_ENERGY_SENSOR_UNIT_PREFIX)
    if unit_prefix == UnitPrefix.NONE:
        unit_prefix = None

    _LOGGER.debug("Creating energy sensor: %s", name)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        entity_category=entity_category,
        name=name,
        round_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
        unit_prefix=unit_prefix,
        unit_time=TIME_HOURS,
        integration_method=sensor_config.get(CONF_ENERGY_INTEGRATION_METHOD)
        or DEFAULT_ENERGY_INTEGRATION_METHOD,
        powercalc_source_entity=source_entity.entity_id,
        powercalc_source_domain=source_entity.domain,
    )


@callback
def find_related_real_energy_sensor(
    hass: HomeAssistant, power_sensor: RealPowerSensor
) -> Optional[RealEnergySensor]:
    """See if a corresponding energy sensor exists in the HA installation for the power sensor"""

    if not power_sensor.device_id:
        return None

    ent_reg = er.async_get(hass)
    energy_sensors = [
        entry
        for entry in er.async_entries_for_device(
            ent_reg, device_id=power_sensor.device_id
        )
        if entry.device_class == SensorDeviceClass.ENERGY
        or entry.unit_of_measurement == ENERGY_KILO_WATT_HOUR
    ]
    if not energy_sensors:
        return None

    return RealEnergySensor(energy_sensors[0])


class EnergySensor:
    """Class which all energy sensors should extend from"""

    pass


class VirtualEnergySensor(IntegrationSensor, EnergySensor, BaseEntity):
    """Virtual energy sensor, totalling kWh"""

    def __init__(
        self,
        source_entity,
        unique_id,
        entity_id,
        entity_category,
        name,
        round_digits,
        unit_prefix,
        unit_time,
        integration_method,
        powercalc_source_entity: str,
        powercalc_source_domain: str,
    ):
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
        self.entity_id = entity_id
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)

    @property
    def extra_state_attributes(self) -> MutableMapping[str, Any]:
        """Return the state attributes of the energy sensor."""
        attrs = {
            ATTR_SOURCE_ENTITY: self._powercalc_source_entity,
            ATTR_SOURCE_DOMAIN: self._powercalc_source_domain,
        }
        attrs.update(super().extra_state_attributes)
        return attrs

    @property
    def icon(self):
        return ENERGY_ICON

    @callback
    def async_reset_energy(self) -> None:
        _LOGGER.debug(f"{self.entity_id}: Reset energy sensor")
        self._state = 0
        self._attr_last_reset = dt_util.utcnow()
        self.async_write_ha_state()


class RealEnergySensor(EnergySensor):
    """Contains a reference to an existing energy sensor entity"""

    def __init__(self, entity_entry: er.RegistryEntry):
        self._entity_entry = entity_entry

    @property
    def entity_id(self) -> str:
        """Return the entity_id of the sensor."""
        return self._entity_entry.entity_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._entity_entry.name or self._entity_entry.original_name

    @property
    def unique_id(self) -> str | None:
        """Return the unique_id of the sensor."""
        return self._entity_entry.unique_id
