from homeassistant.const import CONF_DOMAIN, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import CONF_GROUP_TYPE, GroupType
from custom_components.powercalc.sensors.group.custom import create_group_sensors_custom


async def create_domain_group_sensor(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    domain = config[CONF_DOMAIN]
    if CONF_UNIQUE_ID not in config:
        config[CONF_UNIQUE_ID] = f"powercalc_domaingroup_{domain}"
    name: str = config.get(CONF_NAME, f"All {domain}")
    config[CONF_GROUP_TYPE] = GroupType.DOMAIN
    return await create_group_sensors_custom(
        hass,
        name,
        config,
        set(),
        set(),
        force_create=True,
    )
