from homeassistant.exceptions import HomeAssistantError


class LibraryError(HomeAssistantError):
    """Raised when an error occurred in the library logic."""


class LibraryLoadingError(LibraryError):
    """Raised when an error occurred during library loading."""


class ProfileDownloadError(LibraryError):
    """Raised when an error occurred during profile download."""
