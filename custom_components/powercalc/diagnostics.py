import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import CONF_SENSOR_TYPE, DOMAIN, SensorType
from custom_components.powercalc.sensors.group.config_entry_utils import get_entries_excluding_global_config
from custom_components.powercalc.sensors.group.custom import resolve_entity_ids_recursively

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    data: dict[str, Any] = {
        "entry": entry.as_dict(),
        "config_entry_count_per_type": get_count_by_sensor_type(hass),
        "yaml_config": await get_yaml_configuration(hass),
    }

    if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP:
        data["power_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)
        data["energy_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)

    return data


def get_count_by_sensor_type(hass: HomeAssistant) -> dict[SensorType, int]:
    count_per_type = {}
    entries = get_entries_excluding_global_config(hass)
    for e in entries:
        sensor_type = SensorType(e.data.get(CONF_SENSOR_TYPE, SensorType.VIRTUAL_POWER))
        if sensor_type not in count_per_type:
            count_per_type[sensor_type] = 0
        count_per_type[sensor_type] += 1
    return count_per_type


async def get_yaml_configuration(hass: HomeAssistant) -> ConfigType:
    """Return the YAML configuration for powercalc integration."""
    try:
        yaml_config = await async_integration_yaml_config(hass, DOMAIN)
        return yaml_config.get(DOMAIN, {})  # type: ignore
    except Exception:  # pragma: nocover
        _LOGGER.exception("Could not retrieve YAML config")
        return {}
