from measure.controller.errors import ControllerError


class LightControllerError(ControllerError):
    pass


class ApiConnectionError(LightControllerError):
    pass


class ModelNotDiscoveredError(LightControllerError):
    pass
