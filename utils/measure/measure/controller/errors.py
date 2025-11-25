class ControllerError(Exception):
    pass


class ApiConnectionError(ControllerError):
    """Raised when there is an error connecting to the API."""
