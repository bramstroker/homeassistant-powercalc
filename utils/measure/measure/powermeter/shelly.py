from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.powermeter.shelly_client import ShellyClient, ShellyProbeError


class ShellyPowerMeter(PowerMeter):
    def __init__(
        self,
        shelly_ip: str,
        timeout: int = 5,
        *,
        username: str = "admin",
        password: str | None = None,
        channel: int | None = None,
    ) -> None:
        self._client = ShellyClient(shelly_ip, timeout, username=username, password=password)
        try:
            device = self._client.probe()
            self._component = device.select_power_component(channel)
        except ShellyProbeError as error:
            raise ApiConnectionError(str(error)) from error

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a power reading from the component selected during probing."""
        component = self._component
        if include_voltage and not component.supports_voltage:
            raise UnsupportedFeatureError("Voltage measurement is not supported on this Shelly device")
        try:
            return self._client.read(component, include_voltage=include_voltage)
        except ShellyProbeError as error:
            raise ApiConnectionError(str(error)) from error

    def has_voltage_support(self) -> bool:
        return self._component.supports_voltage
