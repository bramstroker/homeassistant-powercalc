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
    """Create optional utility meters and cost sensor for an energy sensor.

    When cost sensors are enabled, a cost sensor is created for the energy sensor and,
    when utility meters are enabled as well, one additional cost sensor per utility meter.
    """
    entities: list[Entity] = []
    meter_config = sensor_config if utility_meter_config is None else utility_meter_config
    utility_meters = create_utility_meters(hass, energy_sensor, meter_config, config_entry)
    entities.extend(utility_meters)

    cost_sensor = create_cost_sensor_if_needed(hass, sensor_config, energy_sensor, source_entity, cost_name)
    if cost_sensor:
        entities.append(cost_sensor)
        # A cost sensor per utility meter, so each meter cycle (daily, monthly, ...) is priced individually.
        for utility_meter in utility_meters:
            meter_name = utility_meter.name if isinstance(utility_meter.name, str) else None
            # The utility meter resets each cycle, so the cost sensor must reset along with it.
            meter_cost_sensor = create_cost_sensor(
                hass,
                sensor_config,
                utility_meter,
                source_entity,
                meter_name,
                reset_on_source_reset=True,
            )
            if meter_cost_sensor:
                entities.append(meter_cost_sensor)

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
