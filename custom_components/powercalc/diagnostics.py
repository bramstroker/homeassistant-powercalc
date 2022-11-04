from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    return {
        "entry": entry.as_dict(),
    }