import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kasa import Module
from measure.powermeter.kasa import KasaPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult


def test_reads_power_and_voltage_from_energy_module() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.modules = {
        Module.Energy: MagicMock(current_consumption=12.5, voltage=230.4),
    }

    with patch("measure.powermeter.kasa.IotPlug", return_value=plug):
        meter = KasaPowerMeter("192.0.2.1")

    assert asyncio.run(meter.async_read_power_meter()) == (12.5, 230.4)
    plug.update.assert_awaited_once_with()


def test_get_power_creates_its_own_event_loop() -> None:
    plug = MagicMock()
    plug.update = AsyncMock()
    plug.modules = {
        Module.Energy: MagicMock(current_consumption=12.5, voltage=230.4),
    }

    with (
        patch("measure.powermeter.kasa.IotPlug", return_value=plug),
        patch("measure.powermeter.kasa.asyncio.get_event_loop", side_effect=RuntimeError("no current event loop")),
        patch("measure.powermeter.kasa.time.time", return_value=123.0),
    ):
        meter = KasaPowerMeter("192.0.2.1")
        result = meter.get_power(include_voltage=True)

    assert result == PowerMeasurementResult(power=12.5, voltage=230.4, updated=123.0)
