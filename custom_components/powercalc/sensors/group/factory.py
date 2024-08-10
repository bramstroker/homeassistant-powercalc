from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import CONF_CREATE_GROUP, CONF_GROUP_TYPE, GroupType
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.sensors.group.custom import create_group_sensors_gui, create_group_sensors_yaml
from custom_components.powercalc.sensors.group.domain import create_domain_group_sensor
from custom_components.powercalc.sensors.group.standby import create_general_standby_sensors
from custom_components.powercalc.sensors.group.subtract import create_subtract_group_sensors


async def create_group_sensors(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    config_entry: ConfigEntry | None,
    entities: list[Entity] | None = None,
) -> list[Entity]:
    """Create group sensors for a given sensor configuration."""
    group_type: GroupType = GroupType(sensor_config.get(CONF_GROUP_TYPE, GroupType.CUSTOM))
    if group_type == GroupType.DOMAIN:
        return await create_domain_group_sensor(
            hass,
            sensor_config,
        )
    if group_type == GroupType.STANDBY:
        return await create_general_standby_sensors(hass, sensor_config)

    if group_type == GroupType.CUSTOM:
        if config_entry:
            return await create_group_sensors_gui(
                hass=hass,
                entry=config_entry,
                sensor_config=sensor_config,
            )
        return await create_group_sensors_yaml(
            hass=hass,
            group_name=str(sensor_config.get(CONF_CREATE_GROUP)),
            sensor_config=sensor_config,
            entities=entities or [],
        )

    if group_type == GroupType.SUBTRACT:
        return await create_subtract_group_sensors(
            hass=hass,
            config=sensor_config,
        )

    raise SensorConfigurationError(f"Group type {group_type} invalid")  # pragma: no cover
