import logging
from statistics import mean

from measure.execution import ImmediateInteraction, RunInteraction
from measure.request import AverageMeasurementRequest
from measure.util.measure_util import MeasurementResult, MeasureUtil

from .runner import MeasurementRunner, RunnerResult

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


class AverageRunner(MeasurementRunner[AverageMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.duration = 60
        self.interaction = interaction or ImmediateInteraction()

    def run(
        self,
        request: AverageMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.duration = request.duration
        self.interaction.confirm("Ready to start the average measurement.")

        result = self.measure_util.take_average_measurement(self.duration, on_progress=self._report_progress)

        summary = {
            "Average power": f"{round(result.power, 2)} W",
            "Duration": f"{self.duration} s",
        }
        if result.voltages:
            summary["Average voltage"] = f"{round(mean(result.voltages), 1)} V"

        return RunnerResult(model_json_data={}, voltages=result.voltages, summary=summary)

    def _report_progress(self, elapsed: float, duration: float) -> None:
        self.interaction.progress(
            int(min(elapsed, duration)),
            int(duration),
            phase="Averaging",
            remaining_seconds=max(0.0, duration - elapsed),
        )

    def measure_standby_power(self) -> MeasurementResult:
        return MeasurementResult(power=0, voltages=[])
