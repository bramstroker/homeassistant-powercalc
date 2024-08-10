from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_SENSOR_TYPE, SensorType
from custom_components.powercalc.sensors.group.custom import resolve_entity_ids_recursively


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""

    data: dict = {"entry": entry.as_dict()}

    if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP:
        data["power_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.POWER)
        data["energy_entities"] = await resolve_entity_ids_recursively(hass, entry, SensorDeviceClass.ENERGY)

    return data
