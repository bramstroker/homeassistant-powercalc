import logging
from statistics import mean

from measure.profile.fixed import create_fixed_profile_data
from measure.request import AverageMeasurementRequest, FixedMeasurementRequest
from measure.runner.interaction import ImmediateInteraction, RunInteraction
from measure.utils.sampling import PowerSampler

from .runner import MeasurementRunner, RunnerResult

INTERVAL = 2

_LOGGER = logging.getLogger("measure")


class AverageRunner(MeasurementRunner[AverageMeasurementRequest | FixedMeasurementRequest]):
    def __init__(
        self,
        sampler: PowerSampler,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.sampler = sampler
        self.duration = 60
        self.elapsed = 0.0
        self.interaction = interaction or ImmediateInteraction()

    def run(
        self,
        request: AverageMeasurementRequest | FixedMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        self.duration = request.duration
        self.elapsed = float(self.duration)
        self.interaction.phase("Starting averaging")

        result = self.sampler.take_average_measurement(
            self.duration,
            on_progress=self._report_progress,
            finish_on_interrupt=True,
        )

        summary = {
            "Average power": f"{round(result.power, 2)} W",
            "Duration": f"{round(self.elapsed, 1):g} s",
        }
        if result.voltages:
            summary["Average voltage"] = f"{round(mean(result.voltages), 1)} V"

        model_json_data: dict[str, object] = {}
        if isinstance(request, FixedMeasurementRequest):
            model_json_data = create_fixed_profile_data(request.profile_device_type, result.power)

        return RunnerResult(model_json_data=model_json_data, voltages=result.voltages, summary=summary)

    def measure_standby_power(self) -> None:
        """Skip the default zero standby reading, so fixed profiles don't get `standby_power: 0`.

        Power meter profiles set their measured self consumption as standby power themselves.
        """

    def _report_progress(self, elapsed: float, duration: float) -> None:
        self.elapsed = elapsed
        self.interaction.progress(
            int(min(elapsed, duration)),
            int(duration),
            phase="Averaging",
            remaining_seconds=max(0.0, duration - elapsed),
        )
