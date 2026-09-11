import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kasa import AuthenticationError, DeviceConfig, Module
from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.kasa import KasaPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult
import pytest


def test_reads_power_and_voltage_from_energy_module() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.disconnect = AsyncMock()
    plug.modules = {
        Module.Energy: MagicMock(current_consumption=12.5, voltage=230.4),
    }
    plug.config = DeviceConfig(host="192.0.2.1")

    meter = KasaPowerMeter("192.0.2.1")
    with patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)):
        assert asyncio.run(meter.async_read_power_meter()) == (12.5, 230.4)
    plug.update.assert_awaited_once_with()
    plug.disconnect.assert_awaited_once_with()


def test_disconnects_when_a_reading_fails() -> None:
    plug = MagicMock()
    plug.update = AsyncMock(side_effect=OSError("device unreachable"))
    plug.disconnect = AsyncMock()
    plug.config = DeviceConfig(host="192.0.2.1")

    meter = KasaPowerMeter("192.0.2.1")
    with (
        patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)),
        pytest.raises(OSError, match="device unreachable"),
    ):
        asyncio.run(meter.async_read_power_meter())
    plug.disconnect.assert_awaited_once_with()


def test_get_power_creates_its_own_event_loop() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.disconnect = AsyncMock()
    plug.modules = {
        Module.Energy: MagicMock(current_consumption=12.5, voltage=230.4),
    }
    plug.config = DeviceConfig(host="192.0.2.1")

    with (
        patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)),
        patch("measure.powermeter.kasa.asyncio.get_event_loop", side_effect=RuntimeError("no current event loop")),
        patch("measure.powermeter.kasa.time.time", return_value=123.0),
    ):
        meter = KasaPowerMeter("192.0.2.1")
        result = meter.get_power(include_voltage=True)

    assert result == PowerMeasurementResult(power=12.5, voltage=230.4, updated=123.0)


def test_passes_credentials_for_newer_tapo_devices() -> None:
    meter = KasaPowerMeter("192.0.2.1", credentials=("user@example.com", "account-password"))

    discover = AsyncMock(return_value=None)
    with (
        patch("measure.powermeter.kasa.Discover.discover_single", discover),
        pytest.raises(PowerMeterError, match="No Kasa or Tapo device"),
    ):
        asyncio.run(meter.async_read_power_meter())

    credentials = discover.await_args.kwargs["credentials"]
    assert credentials.username == "user@example.com"


def test_reuses_the_discovered_connection_configuration() -> None:
    discovered = MagicMock()
    discovered.update = AsyncMock()
    discovered.disconnect = AsyncMock()
    discovered.modules = {Module.Energy: MagicMock(current_consumption=12.5, voltage=230.4)}
    discovered.config = DeviceConfig(host="192.0.2.1")
    reconnected = MagicMock()
    reconnected.update = AsyncMock()
    reconnected.disconnect = AsyncMock()
    reconnected.modules = {Module.Energy: MagicMock(current_consumption=13.5, voltage=230.4)}
    discover = AsyncMock(return_value=discovered)
    connect = AsyncMock(return_value=reconnected)
    meter = KasaPowerMeter("192.0.2.1")

    with (
        patch("measure.powermeter.kasa.Discover.discover_single", discover),
        patch("measure.powermeter.kasa.Device.connect", connect),
    ):
        assert asyncio.run(meter.async_read_power_meter()) == (12.5, 230.4)
        assert asyncio.run(meter.async_read_power_meter()) == (13.5, 230.4)

    discover.assert_awaited_once_with("192.0.2.1", credentials=None)
    connect.assert_awaited_once()
    assert connect.await_args.kwargs["config"].host == "192.0.2.1"


def test_detects_when_the_device_does_not_support_voltage() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.disconnect = AsyncMock()
    plug.modules = {Module.Energy: MagicMock(current_consumption=12.5, voltage=None)}
    plug.config = DeviceConfig(host="192.0.2.1")
    meter = KasaPowerMeter("192.0.2.1")

    with patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)):
        assert meter.has_voltage_support() is False


def test_rejects_voltage_readings_when_the_device_does_not_expose_voltage() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.disconnect = AsyncMock()
    plug.modules = {Module.Energy: MagicMock(current_consumption=12.5, voltage=None)}
    plug.config = DeviceConfig(host="192.0.2.1")
    meter = KasaPowerMeter("192.0.2.1")

    with (
        patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)),
        pytest.raises(UnsupportedFeatureError, match="does not provide voltage"),
    ):
        meter.get_power(include_voltage=True)


def test_explains_when_a_discovered_device_requires_credentials() -> None:
    plug = MagicMock()
    plug.update = AsyncMock(side_effect=AuthenticationError("authentication required"))
    plug.disconnect = AsyncMock()
    plug.config = DeviceConfig(host="192.0.2.1")
    meter = KasaPowerMeter("192.0.2.1")

    with (
        patch("measure.powermeter.kasa.Discover.discover_single", AsyncMock(return_value=plug)),
        pytest.raises(PowerMeterError, match="requires TP-Link account credentials"),
    ):
        asyncio.run(meter.async_read_power_meter())

    plug.disconnect.assert_awaited_once_with()
