from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.analytics.analytics import collect_analytics
from custom_components.powercalc.const import CONF_GROUP_TYPE, DATA_GROUP_TYPES, GroupType
from custom_components.powercalc.errors import SensorConfigurationError
import custom_components.powercalc.sensors.group.custom as custom_group
import custom_components.powercalc.sensors.group.domain as domain_group
import custom_components.powercalc.sensors.group.standby as standby_group
import custom_components.powercalc.sensors.group.subtract as subtract_group
from custom_components.powercalc.sensors.group.tracked_untracked import TrackedPowerSensorFactory


async def create_group_sensors(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    config_entry: ConfigEntry | None,
    entities: list[Entity] | None = None,
) -> list[Entity]:
    """Create group sensors for a given sensor configuration."""
    group_type: GroupType = GroupType(sensor_config.get(CONF_GROUP_TYPE, GroupType.CUSTOM))
    collect_analytics(hass, config_entry).inc(DATA_GROUP_TYPES, group_type)

    if group_type == GroupType.DOMAIN:
        return await domain_group.create_domain_group_sensor(
            hass,
            sensor_config,
        )
    if group_type == GroupType.STANDBY:
        return await standby_group.create_general_standby_sensors(hass, sensor_config)

    if group_type == GroupType.CUSTOM:
        if config_entry:
            return await custom_group.create_group_sensors_gui(
                hass=hass,
                entry=config_entry,
                sensor_config=sensor_config,
            )
        return await custom_group.create_group_sensors_yaml(
            hass=hass,
            sensor_config=sensor_config,
            entities=entities or [],
        )

    if group_type == GroupType.SUBTRACT:
        return await subtract_group.create_subtract_group_sensors(
            hass=hass,
            config=sensor_config,
        )

    if group_type == GroupType.TRACKED_UNTRACKED and config_entry:
        factory = TrackedPowerSensorFactory(hass, config_entry, sensor_config)
        return await factory.create_tracked_untracked_group_sensors()

    raise SensorConfigurationError(f"Group type {group_type} invalid")  # pragma: no cover
