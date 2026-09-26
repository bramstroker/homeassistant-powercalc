class PowerMeterError(Exception):
    pass


class OutdatedMeasurementError(PowerMeterError):
    pass


class ZeroReadingError(PowerMeterError):
    pass


class ZeroPowerReadingError(ZeroReadingError):
    """An unverified zero power reading, distinct from missing voltage."""

    def __init__(self, power: float) -> None:
        super().__init__("0 watt was read from the power meter")
        self.power = power


class ApiConnectionError(PowerMeterError):
    pass


class UnsupportedFeatureError(PowerMeterError):
    pass
