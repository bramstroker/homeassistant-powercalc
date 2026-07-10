"""Normalize discovery info into sensor configuration."""

from __future__ import annotations

from homeassistant.const import CONF_ENTITY_ID
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from custom_components.powercalc.const import (
    CONF_GROUP_TYPE,
    CONF_SENSOR_TYPE,
    DISCOVERY_TYPE,
    DUMMY_ENTITY_ID,
    GroupType,
    PowercalcDiscoveryType,
    SensorType,
)

GROUP_DISCOVERY_TYPES = {
    PowercalcDiscoveryType.DOMAIN_GROUP: GroupType.DOMAIN,
    PowercalcDiscoveryType.STANDBY_GROUP: GroupType.STANDBY,
}


def convert_discovery_info_to_sensor_config(
    discovery_info: DiscoveryInfoType,
) -> ConfigType:
    """Convert discovery info to sensor config."""
    group_type = GROUP_DISCOVERY_TYPES.get(discovery_info[DISCOVERY_TYPE])
    if group_type:
        discovery_info[CONF_GROUP_TYPE] = group_type
        discovery_info[CONF_SENSOR_TYPE] = SensorType.GROUP
        discovery_info[CONF_ENTITY_ID] = DUMMY_ENTITY_ID

    return discovery_info
