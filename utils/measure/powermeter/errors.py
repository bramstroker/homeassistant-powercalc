class PowerMeterError(Exception):
    pass


class OutdatedMeasurementError(PowerMeterError):
    pass


class ConnectionError(PowerMeterError):
    pass