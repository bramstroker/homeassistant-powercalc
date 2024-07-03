from __future__ import annotations

import inspect
import logging
from decimal import Decimal
from typing import cast

import homeassistant.helpers.entity_registry as er
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter.const import (
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
)
from homeassistant.components.utility_meter.select import TariffSelect
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import StateType

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DOMAIN,
)

from .abstract import BaseEntity
from .energy import EnergySensor, RealEnergySensor

_LOGGER = logging.getLogger(__name__)

GENERAL_TARIFF = "general"


async def create_utility_meters(
    hass: HomeAssistant,
    energy_sensor: EnergySensor,
    sensor_config: dict,
    net_consumption: bool = False,
) -> list[VirtualUtilityMeter]:
    """Create the utility meters."""
    if not sensor_config.get(CONF_CREATE_UTILITY_METERS):
        return []

    utility_meters = []

    if DATA_UTILITY not in hass.data:  # pragma: no cover
        hass.data[DATA_UTILITY] = {}

    tariffs = sensor_config.get(CONF_UTILITY_METER_TARIFFS)
    meter_types = sensor_config.get(CONF_UTILITY_METER_TYPES)
    for meter_type in meter_types:  # type: ignore
        tariff_sensors = []

        name = f"{energy_sensor.name} {meter_type}"
        entity_id = f"{energy_sensor.entity_id}_{meter_type}"
        unique_id = None
        if energy_sensor.unique_id:
            unique_id = f"{energy_sensor.unique_id}_{meter_type}"

        # Prevent duplicate creation of utility meter. See #1322
        if isinstance(energy_sensor, RealEnergySensor) and unique_id:
            entity_registry = er.async_get(hass)
            existing_entity_id = entity_registry.async_get_entity_id(
                domain=SENSOR_DOMAIN,
                platform=DOMAIN,
                unique_id=unique_id,
            )
            if existing_entity_id and hass.states.get(existing_entity_id):
                continue  # pragma: no cover

        # Create generic utility meter (no specific tariffs)
        if not tariffs or GENERAL_TARIFF in tariffs:
            utility_meter = await create_utility_meter(
                energy_sensor.entity_id,
                entity_id,
                name,
                sensor_config,
                meter_type,
                unique_id,
                net_consumption=net_consumption,
            )
            tariff_sensors.append(utility_meter)
            utility_meters.append(utility_meter)

        # Create utility meter for each tariff, and the tariff select entity which allows you to select a tariff.
        if tariffs:
            filtered_tariffs = [t for t in list(tariffs) if t != GENERAL_TARIFF]
            tariff_select = await create_tariff_select(
                filtered_tariffs,
                hass,
                name,
                unique_id,
            )

            for tariff in filtered_tariffs:
                utility_meter = await create_utility_meter(
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

        hass.data[DATA_UTILITY][entity_id] = {DATA_TARIFF_SENSORS: tariff_sensors}

    return utility_meters


async def create_tariff_select(
    tariffs: list,
    hass: HomeAssistant,
    name: str,
    unique_id: str | None,
) -> TariffSelect:
    """Create tariff selection entity."""
    _LOGGER.debug("Creating utility_meter tariff select: %s", name)

    select_component = cast(EntityComponent, hass.data[SELECT_DOMAIN])
    select_unique_id = None
    if unique_id:
        select_unique_id = f"{unique_id}_select"

    tariff_select = TariffSelect(
        name,
        tariffs,
        select_unique_id,
    )

    await select_component.async_add_entities([tariff_select])

    return tariff_select


async def create_utility_meter(
    source_entity: str,
    entity_id: str,
    name: str,
    sensor_config: dict,
    meter_type: str,
    unique_id: str | None = None,
    tariff: str | None = None,
    tariff_entity: str | None = None,
    net_consumption: bool = False,
) -> VirtualUtilityMeter:
    """Create a utility meter entity, one per tariff."""
    parent_meter = entity_id
    if tariff:
        name = f"{name} {tariff}"
        entity_id = f"{entity_id}_{tariff}"
        if unique_id:
            unique_id = f"{unique_id}_{tariff}"

    _LOGGER.debug("Creating utility_meter sensor: %s (entity_id=%s)", name, entity_id)

    params = {
        "source_entity": source_entity,
        "name": name,
        "meter_type": meter_type,
        "meter_offset": sensor_config.get(CONF_UTILITY_METER_OFFSET),
        "net_consumption": net_consumption,
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
    if "periodically_resetting" in signature.parameters:
        params["periodically_resetting"] = False
    if "sensor_always_available" in signature.parameters:
        params["sensor_always_available"] = sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE) or False

    utility_meter = VirtualUtilityMeter(**params)  # type: ignore[no-untyped-call]
    utility_meter.rounding_digits = sensor_config.get(CONF_ENERGY_SENSOR_PRECISION)  # type: ignore
    utility_meter.entity_id = entity_id

    return utility_meter


class VirtualUtilityMeter(UtilityMeterSensor, BaseEntity):
    rounding_digits: int = DEFAULT_ENERGY_SENSOR_PRECISION

    @property
    def unique_id(self) -> str | None:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def native_value(self) -> Decimal | StateType:
        """Return the state of the sensor."""
        if self.rounding_digits and self._state is not None:
            return round(self._state, self.rounding_digits)

        return self._state
