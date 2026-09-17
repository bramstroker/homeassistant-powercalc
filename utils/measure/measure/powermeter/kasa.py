import asyncio
import time

from kasa import AuthenticationError, Credentials, Device, DeviceConfig, Discover, KasaException, Module
from kasa.iot import IotPlug

from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter


class KasaPowerMeter(PowerMeter):
    def __init__(self, device_ip: str, *, credentials: tuple[str, str] | None = None) -> None:
        self._device_ip = device_ip
        self._credentials = Credentials(*credentials) if credentials is not None else None
        self._device_config: DeviceConfig | None = None
        self._voltage_supported: bool | None = None

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a new Kasa or Tapo power reading. Optionally include voltage."""
        power, voltage = asyncio.run(self.async_read_power_meter())

        if include_voltage:
            if voltage is None:
                raise UnsupportedFeatureError("The Kasa or Tapo device does not provide voltage measurements")
            return PowerMeasurementResult(power=power, voltage=voltage, updated=time.time())
        return PowerMeasurementResult(power=power, updated=time.time())

    async def async_read_power_meter(self) -> tuple[float, float | None]:
        device: Device | None = None
        try:
            try:
                device = await self._connect()
                await device.update()
            except AuthenticationError as error:
                if self._credentials is None:
                    message = "This Kasa or Tapo device requires TP-Link account credentials"
                else:
                    message = "TP-Link account authentication failed; verify the configured credentials"
                raise PowerMeterError(message) from error
            except KasaException as error:
                # Encrypted Tapo/Kasa transports can occasionally return a response from
                # a stale session (for example, an invalid-padding decryption error).
                # Normalize it so the measurement engine can retry with a new connection.
                raise PowerMeterError(f"Unable to read power from Kasa or Tapo device: {error}") from error
            assert device is not None
            energy = device.modules.get(Module.Energy)
            if energy is None:
                raise PowerMeterError("The Kasa or Tapo device does not provide energy monitoring")
            power = energy.current_consumption
            if power is None:
                raise PowerMeterError("The Kasa or Tapo device did not return a power measurement")
            voltage = getattr(energy, "voltage", None)
            self._voltage_supported = voltage is not None
            return float(power), float(voltage) if voltage is not None else None
        finally:
            if device is not None:
                await device.disconnect()

    async def _connect(self) -> Device:
        """Discover once, then reconnect directly with the discovered protocol settings."""
        if self._device_config is not None:
            return await Device.connect(config=self._device_config)

        try:
            device = await Discover.discover_single(self._device_ip, credentials=self._credentials)
        except TimeoutError:
            # Legacy Kasa devices use a direct TCP connection. Keep this fallback for
            # networks that permit TCP to the plug but block UDP discovery broadcasts.
            device = IotPlug(self._device_ip)
        if device is None:
            raise PowerMeterError(f"No Kasa or Tapo device was discovered at {self._device_ip}")
        # A DeviceConfig is independent of the live connection and can safely cross the
        # short-lived event loops created by get_power(). It retains the detected protocol,
        # transport, and credentials, so later samples do not require UDP discovery.
        self._device_config = DeviceConfig.from_dict(device.config.to_dict())
        return device

    def has_voltage_support(self) -> bool:
        if self._voltage_supported is None:
            # The initial probe also caches the connection configuration, so the first
            # real sample connects directly instead of broadcasting discovery again.
            asyncio.run(self.async_read_power_meter())
        return bool(self._voltage_supported)
