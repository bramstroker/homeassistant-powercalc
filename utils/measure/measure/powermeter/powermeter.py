from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NamedTuple


class PowerMeter(ABC):
    @abstractmethod
    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a power measurement from the meter. Optionally include voltage readings."""

    @abstractmethod
    def has_voltage_support(self) -> bool:
        """Returns bool depending on the powermeter capabilities to act as a voltmeter."""

    def diagnostic_sample(self) -> PowerMeterDiagnosticSample:
        """Return one raw-enough sample for connection and quality diagnostics."""

        reading = self.get_power(include_voltage=False)
        return PowerMeterDiagnosticSample(
            power=reading.power,
            raw_value=str(reading.power),
            reported_at=reading.updated,
        )


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
    voltage: float | None = None


@dataclass(frozen=True)
class PowerMeterDiagnosticSample:
    power: float
    raw_value: str
    reported_at: float
