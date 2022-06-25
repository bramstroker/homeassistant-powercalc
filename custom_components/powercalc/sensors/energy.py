from __future__ import annotations

import logging
from typing import Any, Optional

import homeassistant.helpers.entity_registry as er
from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME, ENERGY_KILO_WATT_HOUR, TIME_HOURS
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory, async_generate_entity_id
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_POWER_SENSOR_ID,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
)
from custom_components.powercalc.migrate import async_migrate_entity_id
from custom_components.powercalc.sensors.power import PowerSensor, RealPowerSensor

ENERGY_ICON = "mdi:lightning-bolt"
ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)


async def create_energy_sensor(
    hass: HomeAssistantType,
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
    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = sensor_config.get(CONF_NAME) or source_entity.name
    if CONF_ENERGY_SENSOR_FRIENDLY_NAMING in sensor_config:
        friendly_name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_FRIENDLY_NAMING)
        name = friendly_name_pattern.format(name)
    else:
        name = name_pattern.format(name)
    object_id = sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        ENTITY_ID_FORMAT, name_pattern.format(object_id), hass=hass
    )
    entity_category = sensor_config.get(CONF_ENERGY_SENSOR_CATEGORY)
    unique_id = None
    if power_sensor.unique_id:
        unique_id = f"{power_sensor.unique_id}_energy"
        async_migrate_entity_id(hass, SENSOR_DOMAIN, unique_id, entity_id)

    _LOGGER.debug("Creating energy sensor: %s", name)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=unique_id,
        entity_id=entity_id,
        entity_category=entity_category,
        name=name,
        round_digits=sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
        unit_prefix="k",
        unit_of_measurement=None,
        unit_time=TIME_HOURS,
        integration_method=sensor_config.get(CONF_ENERGY_INTEGRATION_METHOD)
        or DEFAULT_ENERGY_INTEGRATION_METHOD,
        powercalc_source_entity=source_entity.entity_id,
        powercalc_source_domain=source_entity.domain,
    )


@callback
def find_related_real_energy_sensor(
    hass: HomeAssistantType, power_sensor: RealPowerSensor
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
    """Class which all power sensors should extend from"""

    pass


class VirtualEnergySensor(IntegrationSensor, EnergySensor):
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
        unit_of_measurement,
        integration_method,
        powercalc_source_entity: str,
        powercalc_source_domain: str,
    ):
        if AwesomeVersion(HA_VERSION) >= AwesomeVersion("2022.5.0.dev0"):
            super().__init__(
                source_entity=source_entity,
                name=name,
                round_digits=round_digits,
                unit_prefix=unit_prefix,
                unit_time=unit_time,
                integration_method=integration_method,
                unique_id=unique_id,
            )
        elif AwesomeVersion(HA_VERSION) >= AwesomeVersion("2022.4.0.dev0"):
            super().__init__(
                source_entity=source_entity,
                name=name,
                round_digits=round_digits,
                unit_prefix=unit_prefix,
                unit_time=unit_time,
                unit_of_measurement=unit_of_measurement,
                integration_method=integration_method,
                unique_id=unique_id,
            )
        else:
            super().__init__(
                source_entity=source_entity,
                name=name,
                round_digits=round_digits,
                unit_prefix=unit_prefix,
                unit_time=unit_time,
                unit_of_measurement=unit_of_measurement,
                integration_method=integration_method,
            )
            if unique_id:
                self._attr_unique_id = unique_id

        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self.entity_id = entity_id
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the acceleration sensor."""
        state_attr = super().extra_state_attributes
        state_attr[ATTR_SOURCE_ENTITY] = self._powercalc_source_entity
        state_attr[ATTR_SOURCE_DOMAIN] = self._powercalc_source_domain
        return state_attr

    @property
    def icon(self):
        return ENERGY_ICON

    @callback
    def async_reset_energy(self) -> None:
        _LOGGER.debug(f"{self.entity_id}: Reset energy sensor")
        self._state = 0
        self.async_write_ha_state()


class RealEnergySensor(EnergySensor):
    """Contains a reference to a existing energy sensor entity"""

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
