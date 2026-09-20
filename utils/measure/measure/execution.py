from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Protocol

from measure.analyser.execution import RecorderAnalysisExecution
from measure.analyser.service import RecorderAnalyser
from measure.const import DUMMY_LOAD_MEASUREMENT_COUNT, DUMMY_LOAD_MEASUREMENTS_DURATION, Trend
from measure.dummy_load import DummyLoadCalibration
from measure.profile.model_json import write_model_json
from measure.request import (
    DummyLoadRequest,
    DummyLoadReuseRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    RecorderPurpose,
)
from measure.runner.interaction import ImmediateInteraction, RunInteraction
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.utils.sampling import PowerSampler


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
    sampler: PowerSampler
    calibration_store: DummyLoadCalibrationStore | None = None

    def run(self, interaction: RunInteraction) -> None:
        self.sampler.validate_dummy_load_support()
        calibrated = False
        resistance = self._load_restored_resistance()
        target = "light" if self.request.measure_type == "light" else "target device"

        if resistance is None:
            interaction.phase("Preparing dummy-load calibration")
            interaction.confirm(
                f"Disconnect the {target} from the power meter. Connect only the preheated resistive dummy load "
                f"({self.spec.description}) before starting calibration.",
                action="Start dummy-load calibration",
            )
            resistance = self.calibrate(interaction)
            calibrated = True
        else:
            interaction.phase("Preparing resistive dummy load")
            interaction.confirm(
                f"Connect the same preheated resistive dummy load ({self.spec.description}) to the power meter.",
            )

        self.sampler.set_dummy_load_resistance(resistance)
        if calibrated and self.calibration_store is not None:
            self.calibration_store.save(self.request, resistance)
        completion = "Dummy-load calibration is complete. " if calibrated else ""
        interaction.confirm(
            f"{completion}Connect the {target} in parallel with the dummy load, and keep the dummy load connected "
            "during the measurement.",
            action="Start measurement",
        )

    def _load_restored_resistance(self) -> float | None:
        if isinstance(self.spec, DummyLoadReuseRequest):
            return self.spec.resistance
        if self.calibration_store is None:
            return None
        calibration = self.calibration_store.load(self.request)
        if calibration is None:
            return None
        return calibration.resistance

    def calibrate(self, interaction: RunInteraction) -> float:
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
                average = self.sampler.take_average_measurement(
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
            trend = self.sampler.classify_dummy_load_trend(averages)
            assert trend is not None  # Calibration always collects the required 20 samples.
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
        analyser: RecorderAnalyser | None = None,
    ) -> None:
        self.measurement = measurement
        self.output_directory = (
            output_directory
            if output_directory is not None
            and (measurement.request.generate_model_json or measurement.runner.writes_export_files())
            else None
        )
        self.analyser = analyser or RecorderAnalyser()

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
            if (
                isinstance(request, RecorderMeasurementRequest)
                and request.recorder_purpose == RecorderPurpose.COMPLEX_PROFILE
                and output_directory is not None
            ):
                self.measurement.interaction.phase("Analysing recording")
                result = RunnerResult(
                    model_json_data=result.model_json_data,
                    voltages=result.voltages,
                    summary=RecorderAnalysisExecution(self.analyser).run(
                        request,
                        output_directory,
                        summary=result.summary,
                        voltages=result.voltages,
                    ),
                )
            if request.generate_model_json and output_directory is not None:
                self._write_model(output_directory, runner, request, result)
            return result
        finally:
            runner.cleanup()

    def _write_model(
        self,
        output_directory: Path,
        runner: MeasurementRunner[Any],
        request: MeasurementRequest,
        result: RunnerResult,
    ) -> None:
        standby = runner.measure_standby_power()
        voltages = list(result.voltages or []) + (standby.voltages if standby is not None else [])
        write_model_json(
            output_directory,
            standby_power=standby.power if standby is not None else None,
            name=request.model_name,
            measure_device=request.measure_device,
            parameters=request.parameters,
            extra_json_data=result.model_json_data,
            voltages=voltages,
            num_lights=request.multiple_light_count if isinstance(request, LightMeasurementRequest) else None,
            dummy_load=request.dummy_load is not None,
            dummy_load_resistance=self._get_dummy_load_resistance(),
        )

    def _get_dummy_load_resistance(self) -> float | None:
        if isinstance(self.measurement.request.dummy_load, DummyLoadReuseRequest):
            return self.measurement.request.dummy_load.resistance
        for preparation in self.measurement.preparations:
            if isinstance(preparation, DummyLoadPreparation):  # pragma: no branch - only concrete preparation type
                return preparation.sampler.dummy_load_value
        return None
