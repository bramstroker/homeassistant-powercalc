import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kasa import Module
from measure.powermeter.kasa import KasaPowerMeter


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
