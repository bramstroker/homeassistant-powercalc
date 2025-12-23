from __future__ import annotations

from decimal import Decimal
import inspect
import logging

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter import DEFAULT_OFFSET
from homeassistant.components.utility_meter.const import (
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
)
from homeassistant.components.utility_meter.select import TariffSelect
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import async_generate_entity_id
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import StateType

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DOMAIN,
)
from custom_components.powercalc.select import DATA_PENDING_SELECT_ENTITIES, SIGNAL_CREATE_SELECT_ENTITIES

from .abstract import BaseEntity
from .energy import EnergySensor, RealEnergySensor

_LOGGER = logging.getLogger(__name__)

GENERAL_TARIFF = "general"


async def create_utility_meters(
    hass: HomeAssistant,
    energy_sensor: EnergySensor,
    sensor_config: dict,
    config_entry: ConfigEntry | None = None,
) -> list[VirtualUtilityMeter]:
    """Create the utility meters."""
    if not sensor_config.get(CONF_CREATE_UTILITY_METERS):
        return []

    if DATA_UTILITY not in hass.data:  # pragma: no cover
        hass.data[DATA_UTILITY] = {}

    tariffs = list(sensor_config.get(CONF_UTILITY_METER_TARIFFS, []))
    meter_types = list(sensor_config.get(CONF_UTILITY_METER_TYPES, []))

    utility_meters = []
    for meter_type in meter_types:
        unique_id = f"{energy_sensor.unique_id}_{meter_type}" if energy_sensor.unique_id else None
        if should_create_utility_meter(hass, unique_id, energy_sensor):
            utility_meters.extend(
                await create_meters_for_type(
                    hass,
                    energy_sensor,
                    sensor_config,
                    config_entry,
                    unique_id,
                    meter_type,
                    tariffs,
                ),
            )

    return utility_meters


def should_create_utility_meter(
    hass: HomeAssistant,
    unique_id: str | None,
    energy_sensor: EnergySensor,
) -> bool:
    """
    Check if a utility meter should be created.
    Prevent duplicate creation of utility meter. See #1322
    """

    if not isinstance(energy_sensor, RealEnergySensor) or not unique_id:
        return True

    entity_registry = er.async_get(hass)
    existing_entity_id = entity_registry.async_get_entity_id(
        domain=SENSOR_DOMAIN,
        platform=DOMAIN,
        unique_id=unique_id,
    )
    return not (existing_entity_id and hass.states.get(existing_entity_id))  # pragma: no cover


async def create_meters_for_type(
    hass: HomeAssistant,
    energy_sensor: EnergySensor,
    sensor_config: dict,
    config_entry: ConfigEntry | None,
    unique_id: str | None,
    meter_type: str,
    tariffs: list[str],
) -> list[VirtualUtilityMeter]:
    """Create meters for a specific meter type."""
    name = f"{energy_sensor.name} {meter_type}"
    entity_id = f"{energy_sensor.entity_id}_{meter_type}"

    tariff_sensors = []
    utility_meters = []

    # Create generic utility meter
    if not tariffs or GENERAL_TARIFF in tariffs:
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

    # Create tariff-specific utility meters
    if tariffs:
        new_tariff_sensors = await create_tariff_meters(
            hass,
            energy_sensor,
            entity_id,
            name,
            sensor_config,
            config_entry,
            meter_type,
            unique_id,
            tariffs,
        )
        tariff_sensors.extend(new_tariff_sensors)
        utility_meters.extend(new_tariff_sensors)

    hass.data[DATA_UTILITY][entity_id] = {DATA_TARIFF_SENSORS: tariff_sensors}
    return utility_meters


async def create_tariff_meters(
    hass: HomeAssistant,
    energy_sensor: EnergySensor,
    entity_id: str,
    name: str,
    sensor_config: dict,
    config_entry: ConfigEntry | None,
    meter_type: str,
    unique_id: str | None,
    tariffs: list[str],
) -> list[VirtualUtilityMeter]:
    """Create utility meters for specific tariffs."""
    filtered_tariffs = [t for t in tariffs if t != GENERAL_TARIFF]
    tariff_select = await create_tariff_select(config_entry, filtered_tariffs, hass, name, unique_id)

    tariff_sensors = []
    for tariff in filtered_tariffs:
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

    return tariff_sensors


async def create_tariff_select(
    config_entry: ConfigEntry | None,
    tariffs: list,
    hass: HomeAssistant,
    name: str,
    unique_id: str | None,
) -> TariffSelect:
    """Create tariff selection entity."""
    _LOGGER.debug("Creating utility_meter tariff select: %s", name)

    select_unique_id = None
    if unique_id:
        select_unique_id = f"{unique_id}_select"

    tariff_select = TariffSelect(
        name,
        tariffs,
        unique_id=select_unique_id,
    )
    tariff_select.entity_id = async_generate_entity_id("select.{}", name, hass=hass)

    key = config_entry.entry_id if config_entry else ""
    pending = hass.data[DOMAIN].setdefault(DATA_PENDING_SELECT_ENTITIES, {}).setdefault(key, [])
    pending.append(tariff_select)

    async_dispatcher_send(
        hass,
        SIGNAL_CREATE_SELECT_ENTITIES.format(key),
        [tariff_select],
    )

    return tariff_select


async def create_utility_meter(
    hass: HomeAssistant,
    source_entity: str,
    entity_id: str,
    name: str,
    sensor_config: dict,
    meter_type: str,
    unique_id: str | None = None,
    tariff: str | None = None,
    tariff_entity: str | None = None,
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
        "hass": hass,
        "source_entity": source_entity,
        "name": name,
        "meter_type": meter_type,
        "meter_offset": sensor_config.get(CONF_UTILITY_METER_OFFSET, DEFAULT_OFFSET),
        "net_consumption": bool(sensor_config.get(CONF_UTILITY_METER_NET_CONSUMPTION, False)),
        "tariff": tariff,
        "tariff_entity": tariff_entity,
        "parent_meter": parent_meter,
        "delta_values": False,
        "cron_pattern": None,
        "periodically_resetting": False,
        "sensor_always_available": sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE) or False,
        "unique_id": unique_id,
    }

    signature = inspect.signature(UtilityMeterSensor.__init__)

    params = {key: value for key, value in params.items() if key in signature.parameters}

    utility_meter = VirtualUtilityMeter(**params)  # type: ignore[no-untyped-call]
    utility_meter.rounding_digits = int(sensor_config.get(CONF_ENERGY_SENSOR_PRECISION, DEFAULT_ENERGY_SENSOR_PRECISION))
    utility_meter.entity_id = entity_id

    return utility_meter


class VirtualUtilityMeter(UtilityMeterSensor, BaseEntity):
    rounding_digits: int = DEFAULT_ENERGY_SENSOR_PRECISION

    @property
    def unique_id(self) -> str | None:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested number of decimal digits for display."""
        return self.rounding_digits

    @property
    def native_value(self) -> StateType | Decimal:
        """Return the state of the sensor."""
        value = self._state if hasattr(self, "_state") else self._attr_native_value  # pre HA 2024.12 value was stored in _state
        if self.rounding_digits and value is not None:
            return Decimal(round(value, self.rounding_digits))  # type: ignore

        return value  # type: ignore
