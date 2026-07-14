from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple


class PowerMeter(ABC):
    @abstractmethod
    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        """Get a power measurement from the meter. Optionally include voltage readings."""

    @abstractmethod
    def has_voltage_support(self) -> bool:
        """Returns bool depending on the powermeter capabilities to act as a voltmeter."""


class PowerMeasurementResult(NamedTuple):
    power: float
    updated: float
    voltage: float | None = None
