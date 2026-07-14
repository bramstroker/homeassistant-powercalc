from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Protocol

from measure.model import write_model_json
from measure.request import MeasurementRequest
from measure.runner.runner import MeasurementRunner, RunnerResult


class RunInteraction(Protocol):
    """Adapter boundary for input/output needed while a measurement is running."""

    def confirm(self, message: str) -> None:
        """Wait until the operator confirms that a measurement may continue."""

    def notify(self, message: str) -> None:
        """Present non-terminal run information to the operator."""

    def choose(self, message: str, *, default: bool) -> bool:
        """Ask the operator to make a binary choice."""

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        """Report measurement progress. ``total`` of 0 means the run is open-ended."""

    def wait(self, seconds: float) -> None:
        """Wait for a duration, raising if the run is cancelled."""

    def checkpoint(self) -> None:
        """Raise when the active run has been cancelled."""


class MeasurementCancelledError(Exception):
    """Raised when an active measurement is cancelled cooperatively."""


class ImmediateInteraction:
    """Non-interactive execution adapter used by tests and unattended runs."""

    def confirm(self, _: str) -> None:
        return

    def notify(self, _: str) -> None:
        return

    def choose(self, _: str, *, default: bool) -> bool:
        return default

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        return

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def checkpoint(self) -> None:
        return


@dataclass(frozen=True)
class PreparedMeasurement:
    """Fully assembled measurement graph ready for transport-independent execution."""

    request: MeasurementRequest
    runner: MeasurementRunner[Any]


class MeasurementExecution:
    """Own output, cleanup, standby measurement and model writing for a prepared runner."""

    def __init__(
        self,
        *,
        measurement: PreparedMeasurement,
        output_directory: Path | None,
    ) -> None:
        self.measurement = measurement
        self.output_directory = (
            output_directory
            if output_directory is not None
            and (measurement.request.generate_model_json or measurement.runner.writes_export_files())
            else None
        )

    def run(self) -> RunnerResult:
        """Run and clean the device before measuring standby power and writing the model."""

        output_directory = self.output_directory
        runner = self.measurement.runner
        request = self.measurement.request
        if output_directory is None and (request.generate_model_json or runner.writes_export_files()):
            raise ValueError("An output directory is required for a measurement that writes files")
        if output_directory is not None:
            output_directory.mkdir(parents=True, exist_ok=True)
        try:
            result = runner.run(request, str(output_directory or ""))
        finally:
            runner.cleanup()

        if request.generate_model_json and output_directory is not None:
            standby = runner.measure_standby_power()
            write_model_json(
                output_directory,
                standby_power=standby.power,
                name=request.model_name,
                measure_device=request.measure_device,
                parameters=request.parameters,
                extra_json_data=result.model_json_data,
                voltages=list(result.voltages or []) + standby.voltages,
            )
        return result
