from __future__ import annotations

from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.powermeter.shelly_client import ShellyClient, ShellyDevice, ShellyProbeError


class ShellyPowerMeter(PowerMeter):
    def __init__(self, shelly_ip: str, timeout: int = 5) -> None:
        self._client = ShellyClient(shelly_ip, timeout)
        try:
            self._device: ShellyDevice = self._client.probe()
        except ShellyProbeError as error:
            raise ApiConnectionError(str(error)) from error

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a power reading from the component selected during probing."""
        component = self._device.power_component
        if include_voltage and not component.supports_voltage:
            raise UnsupportedFeatureError("Voltage measurement is not supported on this Shelly device")
        try:
            return self._client.read(component, include_voltage=include_voltage)
        except ShellyProbeError as error:
            raise ApiConnectionError(str(error)) from error

    def has_voltage_support(self) -> bool:
        return self._device.power_component.supports_voltage
