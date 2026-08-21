from measure.controller.errors import ControllerError


class LightControllerError(ControllerError):
    pass


class ModelNotDiscoveredError(LightControllerError):
    pass
