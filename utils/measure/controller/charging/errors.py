from controller.errors import ControllerError


class ChargingControllerError(ControllerError):
    pass


class BatteryLevelRetrievalError(ChargingControllerError):
    pass
