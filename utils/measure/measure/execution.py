from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from measure.const import QUESTION_DUMMY_LOAD
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasureUtil


class RunInteraction(Protocol):
    """Adapter boundary for input/output needed while a measurement is running."""

    def confirm(self, message: str) -> None:
        """Wait until the operator confirms that a measurement may continue."""

    def notify(self, message: str) -> None:
        """Present non-terminal run information to the operator."""

    def wait(self, seconds: float) -> None:
        """Wait for a duration, raising if the run is cancelled."""


@dataclass(frozen=True)
class MeasurementMetadata:
    """Shared output settings, independent of the UI that collected them."""

    model_id: str
    model_name: str
    measure_device: str
    generate_model_json: bool


@dataclass(frozen=True)
class ExecutionResult:
    runner_result: RunnerResult
    export_directory: Path | None


class MeasurementExecution:
    """Execute a prepared runner without depending on CLI or web transport details."""

    def __init__(
        self,
        *,
        runner: MeasurementRunner,
        measure_util: MeasureUtil,
        answers: dict[str, Any],
        metadata: MeasurementMetadata,
        output_directory: Path | None,
        interaction: RunInteraction,
        write_model: Callable[[Path, float, str, str, dict[str, Any], list[float]], None],
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self.runner = runner
        self.measure_util = measure_util
        self.answers = answers
        self.metadata = metadata
        self.output_directory = output_directory
        self.interaction = interaction
        self.write_model = write_model
        self.cleanup = cleanup

    def run(self) -> ExecutionResult:
        self.runner.prepare(self.answers)
        if self.answers.get(QUESTION_DUMMY_LOAD, False):
            self.measure_util.initialize_dummy_load()
            self.interaction.confirm(
                "Please connect the appliance in parallel to the dummy load and confirm to start measurement.",
            )

        export_directory = self.output_directory
        if export_directory is not None:
            export_directory.mkdir(parents=True, exist_ok=True)

        try:
            result = self.runner.run(self.answers, str(export_directory or ""))
            if result is None:
                raise RuntimeError("Measurement runner did not return a result")
            if self.metadata.generate_model_json and export_directory is not None:
                standby = self.runner.measure_standby_power()
                self.write_model(
                    export_directory,
                    standby.power,
                    self.metadata.model_name,
                    self.metadata.measure_device,
                    result.model_json_data,
                    list(result.voltages or []) + standby.voltages,
                )
            return ExecutionResult(runner_result=result, export_directory=export_directory)
        finally:
            if self.cleanup is not None:
                self.cleanup()
