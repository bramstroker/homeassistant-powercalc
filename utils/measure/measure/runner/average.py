import logging
from statistics import mean

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
            power = round(result.power, 4)
            if power <= 0:
                raise ValueError("No positive self consumption was measured; check the meter and device")
            if request.profile_device_type.value == "power_meter" and power < 0.05:
                raise ValueError("Power meter self consumption must be at least 0.05 W for a valid profile")
            model_json_data = {
                "device_type": request.profile_device_type.value,
                "calculation_strategy": "fixed",
                "discovery_by": "device",
            }
            if request.profile_device_type.value == "power_meter":
                model_json_data.update({"standby_power": power, "only_self_usage": True})
            else:
                model_json_data["fixed_config"] = {"power": power}

        return RunnerResult(model_json_data=model_json_data, voltages=result.voltages, summary=summary)

    def measure_standby_power(self) -> None:
        """Averaging measures one operating state, with no separate standby reading."""

    def _report_progress(self, elapsed: float, duration: float) -> None:
        self.elapsed = elapsed
        self.interaction.progress(
            int(min(elapsed, duration)),
            int(duration),
            phase="Averaging",
            remaining_seconds=max(0.0, duration - elapsed),
        )
