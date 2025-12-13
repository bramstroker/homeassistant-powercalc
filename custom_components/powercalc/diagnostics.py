import logging

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.reload import async_integration_yaml_config

from custom_components.powercalc import CONF_SENSOR_TYPE, DOMAIN, SensorType
from custom_components.powercalc.analytics.collection import get_count_by_sensor_type
from custom_components.powercalc.sensors.group.custom import resolve_entity_ids_recursively

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""

    data: dict = {
        "entry": entry.as_dict(),
        "config_entry_count_per_type": await get_count_by_sensor_type(hass),
        "yaml_config": await get_yaml_configuration(hass),
    }

    if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP:
        data["power_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)
        data["energy_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)

    return data


async def get_yaml_configuration(hass: HomeAssistant) -> dict:
    """Return the YAML configuration for powercalc integration."""
    try:
        yaml_config = await async_integration_yaml_config(hass, DOMAIN)
        return yaml_config.get(DOMAIN, {})  # type: ignore
    except Exception as err:  # noqa: BLE001  # pragma: nocover
        _LOGGER.error("Could not retrieve YAML config: %s", err)
        return {}
