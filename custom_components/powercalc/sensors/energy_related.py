from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_CREATE_COST_SENSOR

from .cost import create_cost_sensor
from .energy import EnergySensor
from .utility_meter import create_utility_meters


def create_energy_related_sensors(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    energy_sensor: EnergySensor,
    source_entity: SourceEntity | None = None,
    config_entry: ConfigEntry | None = None,
    utility_meter_config: ConfigType | None = None,
    cost_name: str | None = None,
) -> list[Entity]:
    """Create optional utility meters and cost sensor for an energy sensor."""
    entities: list[Entity] = []
    meter_config = sensor_config if utility_meter_config is None else utility_meter_config
    entities.extend(create_utility_meters(hass, energy_sensor, meter_config, config_entry))

    cost_sensor = create_cost_sensor_if_needed(hass, sensor_config, energy_sensor, source_entity, cost_name)
    if cost_sensor:
        entities.append(cost_sensor)

    return entities


def create_cost_sensor_if_needed(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    energy_sensor: EnergySensor,
    source_entity: SourceEntity | None = None,
    name: str | None = None,
) -> Entity | None:
    """Create a cost sensor when enabled and configured."""
    if not sensor_config.get(CONF_CREATE_COST_SENSOR):
        return None
    return create_cost_sensor(hass, sensor_config, energy_sensor, source_entity, name)
