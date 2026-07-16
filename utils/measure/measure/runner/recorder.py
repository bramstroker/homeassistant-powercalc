import csv
import logging
from pathlib import Path
import time

from measure.execution import ImmediateInteraction, MeasurementCancelledError, RunInteraction
from measure.request import RecorderMeasurementRequest, validate_export_filename
from measure.runner.const import DEFAULT_EXPORT_FILENAME
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.util.measure_util import MeasurementResult, MeasureUtil

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


class RecorderRunner(MeasurementRunner[RecorderMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.filename = DEFAULT_EXPORT_FILENAME
        self.interaction = interaction or ImmediateInteraction()

    def writes_export_files(self) -> bool:
        return True

    def run(
        self,
        request: RecorderMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.filename = validate_export_filename(request.export_filename)
        self.interaction.confirm("Ready to start recording. Stop the measurement when you are finished.")
        self.interaction.phase("Starting recording")

        output_directory = Path(export_directory).resolve()
        csv_filepath = (output_directory / self.filename).resolve()
        if not csv_filepath.is_relative_to(output_directory):
            raise ValueError("Recorder export path escapes its output directory")
        start_time = time.time()
        voltages: list[float] = []
        recorded = 0
        # Stopping a recorder (KeyboardInterrupt on the CLI, cancellation in the app) is the
        # normal way to finish it, so we treat it as a successful completion, not a cancel.
        try:
            with csv_filepath.open("w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                while True:
                    timestamp = time.time()
                    self.interaction.notify("Measurement")
                    measurement = self.measure_util.take_measurement(timestamp)
                    _LOGGER.info("Measurement %.2f", measurement.power)
                    writer.writerow([timestamp - start_time, measurement.power])
                    voltages.extend(measurement.voltages)
                    recorded += 1
                    # Open-ended recording: report the running sample count (total 0 = indeterminate).
                    self.interaction.progress(recorded, 0, phase="Recording")
                    self.interaction.wait(INTERVAL)
        except KeyboardInterrupt, MeasurementCancelledError:
            _LOGGER.info("Stopped recording")

        summary = {
            "Samples recorded": str(recorded),
            "Duration": f"{round(time.time() - start_time)} s",
        }
        return RunnerResult(model_json_data={}, voltages=voltages, summary=summary)

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])
