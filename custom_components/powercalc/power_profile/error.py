from homeassistant.exceptions import HomeAssistantError


class ProfileDownloadError(HomeAssistantError):
    """Raised when an error occured during library download."""
