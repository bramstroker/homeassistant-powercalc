from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from measure.request import BaseMeasurementRequest
from measure.util.measure_util import MeasurementResult


class MeasurementRunner[TRequest: BaseMeasurementRequest](ABC):
    """Lifecycle contract for a measurement strategy and request type."""

    @abstractmethod
    def run(
        self,
        request: TRequest,
        export_directory: str,
    ) -> RunnerResult:
        """Execute the active measurement and return profile post-processing data."""
        ...

    def writes_export_files(self) -> bool:
        return False

    def cleanup(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Release runner-owned resources after execution."""

    def measure_standby_power(self) -> MeasurementResult:
        """Measure idle power after cleanup when the strategy supports it."""

        return MeasurementResult(power=0, voltages=[])


@dataclass
class RunnerResult:
    """Runner output consumed by profile generation and session summaries."""

    model_json_data: dict[str, Any]
    voltages: list[float] | None = None
    summary: dict[str, str] | None = None
