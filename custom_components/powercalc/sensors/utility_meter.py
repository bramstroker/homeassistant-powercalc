from __future__ import annotations

import inspect
import logging
from typing import cast

from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.const import __version__ as HA_VERSION

if AwesomeVersion(HA_VERSION) >= AwesomeVersion("2022.4.0.dev0"):
    from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
    from homeassistant.components.utility_meter.select import TariffSelect
else:
    from homeassistant.components.utility_meter import TariffSelect

from homeassistant.components.utility_meter.const import (
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
)
from homeassistant.components.utility_meter.const import DOMAIN as UTILITY_DOMAIN
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.const import __short_version__
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import HomeAssistantType

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_SENSOR_PRECISION,
)
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.migrate import async_set_unique_id
from custom_components.powercalc.sensors.energy import EnergySensor

_LOGGER = logging.getLogger(__name__)


async def create_utility_meters(
    hass: HomeAssistantType,
    energy_sensor: EnergySensor,
    sensor_config: dict,
) -> list[UtilityMeterSensor]:
    """Create the utility meters"""
    utility_meters = []

    if not sensor_config.get(CONF_CREATE_UTILITY_METERS):
        return []

    if not DATA_UTILITY in hass.data:
        hass.data[DATA_UTILITY] = {}

    tariffs = sensor_config.get(CONF_UTILITY_METER_TARIFFS)
    meter_types = sensor_config.get(CONF_UTILITY_METER_TYPES)
    for meter_type in meter_types:
        tariff_sensors = []

        name = f"{energy_sensor.name} {meter_type}"
        entity_id = f"{energy_sensor.entity_id}_{meter_type}"
        unique_id = None
        if energy_sensor.unique_id:
            unique_id = f"{energy_sensor.unique_id}_{meter_type}"

        if tariffs:
            tariff_select = await create_tariff_select(tariffs, hass, name, unique_id)

            for tariff in tariffs:
                utility_meter = await create_utility_meter(
                    hass,
                    energy_sensor.entity_id,
                    entity_id,
                    name,
                    sensor_config,
                    meter_type,
                    unique_id,
                    tariff,
                    tariff_select.entity_id,
                )
                tariff_sensors.append(utility_meter)
                utility_meters.append(utility_meter)

        else:
            utility_meter = await create_utility_meter(
                hass,
                energy_sensor.entity_id,
                entity_id,
                name,
                sensor_config,
                meter_type,
                unique_id,
            )
            tariff_sensors.append(utility_meter)
            utility_meters.append(utility_meter)

        hass.data[DATA_UTILITY][entity_id] = {DATA_TARIFF_SENSORS: tariff_sensors}

    return utility_meters


async def create_tariff_select(
    tariffs: list, hass: HomeAssistantType, name: str, unique_id: str | None
):
    """Create tariff selection entity"""

    _LOGGER.debug(f"Creating utility_meter tariff select: {name}")
    utility_meter_component = cast(
        EntityComponent, hass.data["entity_components"].get(UTILITY_DOMAIN)
    )
    if utility_meter_component is None:
        utility_meter_component = (
            hass.data.get("utility_meter_legacy_component") or None
        )

    if utility_meter_component is None:
        raise SensorConfigurationError("Cannot find utility_meter component")

    if AwesomeVersion(HA_VERSION) >= AwesomeVersion("2022.4.0.dev0"):
        select_component = cast(EntityComponent, hass.data[SELECT_DOMAIN])
        if AwesomeVersion(HA_VERSION) >= AwesomeVersion("2022.4.0"):
            select_unique_id = None
            if unique_id:
                select_unique_id = f"{unique_id}_select"
            tariff_select = TariffSelect(
                name,
                list(tariffs),
                utility_meter_component.async_add_entities,
                select_unique_id,
            )
        else:
            tariff_select = TariffSelect(
                name, list(tariffs), utility_meter_component.async_add_entities
            )
        await select_component.async_add_entities([tariff_select])
    else:
        tariff_select = TariffSelect(name, list(tariffs))
        await utility_meter_component.async_add_entities([tariff_select])

    return tariff_select


async def create_utility_meter(
    hass: HomeAssistantType,
    source_entity: str,
    entity_id: str,
    name: str,
    sensor_config: dict,
    meter_type: str,
    unique_id: str = None,
    tariff: str = None,
    tariff_entity: str = None,
) -> VirtualUtilityMeter:
    """Create a utility meter entity, one per tariff"""

    parent_meter = entity_id
    if tariff:
        name = f"{name} {tariff}"
        entity_id = f"{entity_id}_{tariff}"
        if unique_id:
            unique_id = f"{unique_id}_{tariff}"

    _LOGGER.debug(f"Creating utility_meter sensor: {name} (entity_id={entity_id})")

    params = {
        "source_entity": source_entity,
        "name": name,
        "meter_type": meter_type,
        "meter_offset": sensor_config.get(CONF_UTILITY_METER_OFFSET),
        "net_consumption": False,
        "tariff": tariff,
        "tariff_entity": tariff_entity,
    }

    signature = inspect.signature(UtilityMeterSensor.__init__)
    if "parent_meter" in signature.parameters:
        params["parent_meter"] = parent_meter
    if "delta_values" in signature.parameters:
        params["delta_values"] = False
    if "unique_id" in signature.parameters:
        params["unique_id"] = unique_id
    if "cron_pattern" in signature.parameters:
        params["cron_pattern"] = None

    utility_meter = VirtualUtilityMeter(**params)
    setattr(
        utility_meter,
        "rounding_digits",
        sensor_config.get(CONF_ENERGY_SENSOR_PRECISION),
    )

    # This is for BC purposes, for HA versions lower than 2022.4. May be removed in the future
    if not "unique_id" in params and unique_id:
        # Set new unique id if this entity already exists in the entity registry
        async_set_unique_id(hass, entity_id, unique_id)
        utility_meter.unique_id = unique_id

    utility_meter.entity_id = entity_id

    return utility_meter


class VirtualUtilityMeter(UtilityMeterSensor):
    rounding_digits: int = DEFAULT_ENERGY_SENSOR_PRECISION

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._attr_unique_id

    @unique_id.setter
    def unique_id(self, value):
        """Set unique id."""
        self._attr_unique_id = value

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.rounding_digits and self._state is not None:
            return round(self._state, self.rounding_digits)

        return self._state
