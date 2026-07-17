from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
import time
from typing import Any, Literal, NotRequired, Protocol, TypedDict

from measure.const import DUMMY_LOAD_MEASUREMENT_COUNT, DUMMY_LOAD_MEASUREMENTS_DURATION, Trend
from measure.dummy_load import DummyLoadCalibration
from measure.model import write_model_json
from measure.request import (
    DummyLoadRequest,
    DummyLoadReuseRequest,
    MeasurementRequest,
)
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import DummyLoadMeasurementError, MeasureUtil


class LightOperatingPoint(TypedDict):
    type: Literal["light"]
    on: bool
    brightness: NotRequired[int]
    color_temp_mired: NotRequired[int]
    hue: NotRequired[int]
    saturation: NotRequired[int]
    effect: NotRequired[str]


class SpeakerOperatingPoint(TypedDict):
    type: Literal["speaker"]
    volume: int
    muted: bool


class FanOperatingPoint(TypedDict):
    type: Literal["fan"]
    percentage: int
    on: bool


class ChargingOperatingPoint(TypedDict):
    type: Literal["charging"]
    battery_level: int
    charging: bool


type OperatingPoint = LightOperatingPoint | SpeakerOperatingPoint | FanOperatingPoint | ChargingOperatingPoint


class RunInteraction(Protocol):
    """Full interaction boundary used while a measurement is running."""

    def confirm(self, message: str) -> None:
        """Wait until the user confirms a physical preparation step."""

    def choose(self, message: str, *, default: bool) -> bool:
        """Request a binary runtime choice."""

    def notify(self, message: str) -> None:
        """Report information which does not represent a measurement phase."""

    def phase(self, message: str) -> None:
        """Report the current activity when numeric progress is unavailable."""

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        """Report measurement progress. ``total`` of 0 means the run is open-ended."""

    def wait(self, seconds: float) -> None:
        """Wait for a duration, raising if the run is cancelled."""

    def checkpoint(self) -> None:
        """Raise when the active run has been cancelled."""

    def operating_point(self, point: OperatingPoint) -> None:
        """Report the device state currently being measured."""


class MeasurementCancelledError(Exception):
    """Raised when an active measurement is cancelled cooperatively."""


class ImmediateInteraction(RunInteraction):
    """Non-interactive execution adapter used by tests and unattended runs."""

    def confirm(self, _: str) -> None:
        return

    def notify(self, _: str) -> None:
        return

    def choose(self, _: str, *, default: bool) -> bool:
        return default

    def phase(self, message: str) -> None:
        return

    def progress(self, completed: int, total: int, *, phase: str, remaining_seconds: float | None = None) -> None:
        return

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def checkpoint(self) -> None:
        return

    def operating_point(self, point: OperatingPoint) -> None:
        return


class MeasurementPreparation(Protocol):
    """A physical or runtime prerequisite executed before the measurement runner."""

    def run(self, interaction: RunInteraction) -> None: ...


class DummyLoadCalibrationStore(Protocol):
    """Persistence boundary for restoring and saving a session calibration."""

    def load(self, request: MeasurementRequest) -> DummyLoadCalibration | None:
        """Return a calibration already completed for this resumable session."""

    def save(self, request: MeasurementRequest, resistance: float) -> DummyLoadCalibration:
        """Persist a completed calibration for reuse and session resume."""


@dataclass(frozen=True)
class DummyLoadPreparation(MeasurementPreparation):
    """Calibrate or restore a resistive load before applying its correction."""

    request: MeasurementRequest
    spec: DummyLoadRequest
    measure_util: MeasureUtil
    calibration_store: DummyLoadCalibrationStore | None = None

    def run(self, interaction: RunInteraction) -> None:
        self.measure_util.validate_dummy_load_support()
        calibrated = False
        resistance = self._restored_resistance()

        if resistance is None:
            interaction.phase("Preparing dummy-load calibration")
            interaction.confirm(
                f"Connect only the preheated resistive dummy load ({self.spec.description}) to the power meter.",
            )
            resistance = self._calibrate(interaction)
            calibrated = True
        else:
            interaction.phase("Preparing resistive dummy load")
            interaction.confirm(
                f"Connect the same preheated resistive dummy load ({self.spec.description}) to the power meter.",
            )

        self.measure_util.set_dummy_load_resistance(resistance)
        if calibrated and self.calibration_store is not None:
            self.calibration_store.save(self.request, resistance)
        interaction.confirm(
            "Connect the target device in parallel with the dummy load and keep the dummy load connected.",
        )

    def _restored_resistance(self) -> float | None:
        if isinstance(self.spec, DummyLoadReuseRequest):
            return self.spec.resistance
        if self.calibration_store is None:
            return None
        calibration = self.calibration_store.load(self.request)
        if calibration is None:
            return None
        if calibration.resistance <= 0:
            raise DummyLoadMeasurementError("Restored dummy-load resistance must be positive")
        return calibration.resistance

    def _calibrate(self, interaction: RunInteraction) -> float:
        while True:
            averages: list[float] = []
            for index in range(DUMMY_LOAD_MEASUREMENT_COUNT):
                interaction.checkpoint()
                interaction.progress(
                    index,
                    DUMMY_LOAD_MEASUREMENT_COUNT,
                    phase="Calibrating resistive dummy load",
                    remaining_seconds=(DUMMY_LOAD_MEASUREMENT_COUNT - index) * DUMMY_LOAD_MEASUREMENTS_DURATION,
                )
                average = self.measure_util.take_average_measurement(
                    DUMMY_LOAD_MEASUREMENTS_DURATION,
                    measure_resistance=True,
                )
                averages.append(average.power)
                interaction.notify(
                    f"Dummy-load calibration sample {index + 1}/{DUMMY_LOAD_MEASUREMENT_COUNT}: {average.power:.2f} Ω",
                )

            interaction.progress(
                DUMMY_LOAD_MEASUREMENT_COUNT,
                DUMMY_LOAD_MEASUREMENT_COUNT,
                phase="Checking dummy-load stability",
                remaining_seconds=0,
            )
            trend = self.measure_util.dummy_load_trend(averages)
            if trend is None:
                raise DummyLoadMeasurementError("No dummy-load resistance trend could be calculated")
            if trend == Trend.STEADY:
                resistance = round(mean(averages), 2)
                interaction.phase(f"Dummy-load calibration completed at {resistance:.2f} Ω")
                return resistance
            interaction.phase(f"Dummy-load resistance is still {trend}; repeating calibration")


@dataclass(frozen=True)
class PreparedMeasurement:
    """Fully assembled measurement graph ready for transport-independent execution."""

    request: MeasurementRequest
    runner: MeasurementRunner[Any]
    preparations: list[MeasurementPreparation] = field(default_factory=list)
    interaction: RunInteraction = field(default_factory=ImmediateInteraction)


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
        """Run, optionally write the model, and always clean up runner resources."""

        output_directory = self.output_directory
        runner = self.measurement.runner
        request = self.measurement.request
        if output_directory is None and (request.generate_model_json or runner.writes_export_files()):
            raise ValueError("An output directory is required for a measurement that writes files")
        if output_directory is not None:
            output_directory.mkdir(parents=True, exist_ok=True)
        try:
            for preparation in self.measurement.preparations:
                preparation.run(self.measurement.interaction)
            result = runner.run(request, str(output_directory or ""))
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
        finally:
            runner.cleanup()
