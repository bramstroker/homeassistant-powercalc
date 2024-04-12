from homeassistant.exceptions import HomeAssistantError


class LibraryError(HomeAssistantError):
    """Raised when an error occured in the library logic."""


class LibraryLoadingError(LibraryError):
    """Raised when an error occured during library loading."""


class ProfileDownloadError(LibraryError):
    """Raised when an error occured during profile download."""
