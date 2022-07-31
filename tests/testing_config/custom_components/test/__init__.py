async def async_setup_entry(hass, entry) -> bool:
    """Set up Powercalc integration from a config entry."""
    hass.config_entries.async_setup_platforms(entry, ["light"])
    return True
