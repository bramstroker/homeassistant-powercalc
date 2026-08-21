from measure.controller.errors import ApiConnectionError, ControllerError


class LightControllerError(ControllerError):
    pass


class ModelNotDiscoveredError(LightControllerError):
    pass


# Re-exported so light controllers and the light runner agree on a single class.
# Two separate ApiConnectionError definitions used to exist here and in
# measure.controller.errors, which silently broke `except ApiConnectionError`.
__all__ = ["ApiConnectionError", "LightControllerError", "ModelNotDiscoveredError"]
