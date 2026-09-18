from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import time

from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from measure.request import LightMeasurementRequest
from measure.runner.errors import RunnerError
from measure.runner.interaction import ImmediateInteraction, LightOperatingPoint, RunInteraction
from measure.runner.light.csv import (
    compress_light_csv,
    has_measurement_rows,
    inspect_light_csv,
    open_csv_writer,
    repair_incomplete_csv_tail,
)
from measure.runner.light.plan import (
    ColorTempVariation,
    EffectVariation,
    HsVariation,
    LightMeasurementPlan,
    LightModePlan,
    Variation,
    build_light_plan,
    estimate_light_time_left,
    variations_after,
)
from measure.runner.light.setup import set_light_to_maximum_brightness
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.tuning import MeasurementParameters
from measure.utils.sampling import AverageMeasurementConvergence, MeasurementResult, PowerSampler

MAX_CONSECUTIVE_ZERO_READINGS = 5
ZERO_READING_ABORT_MESSAGE = (
    "Aborting measurement session after repeated 0 W readings. The power meter may not resolve this low load. "
    "Verify the device is on and connected, measure multiple identical lights together, "
    "add a resistive dummy load, or use a more sensitive meter. "
    "See https://docs.powercalc.nl/contributing/measure/troubleshooting/ for troubleshooting guidance."
)

_LOGGER = logging.getLogger("measure")


@dataclass
class LightRunProgress:
    """Track unfinished variations against the full plan, including resumed work."""

    total: int
    remaining: list[Variation]

    @property
    def completed(self) -> int:
        return self.total - len(self.remaining)


class LightRunner(MeasurementRunner[LightMeasurementRequest]):
    """Measure configured light modes and write one LUT CSV per mode."""

    def __init__(
        self,
        sampler: PowerSampler,
        parameters: MeasurementParameters,
        light_controller: LightController,
        interaction: RunInteraction | None = None,
        *,
        resume: bool = False,
    ) -> None:
        self.light_controller = light_controller
        self.sampler = sampler
        self.lut_modes: set[LutMode] | None = None
        self.num_lights: int = 1
        self.num_0_readings: int = 0
        self.skipped_zero_readings: int = 0
        self.light_info: LightInfo | None = None
        self.plan: LightMeasurementPlan | None = None
        self.active_plan: LightMeasurementPlan | None = None
        self.config = parameters
        self.gzip = True
        self.interaction = interaction or ImmediateInteraction()
        self._resume = resume

    def _wait(self, seconds: float) -> None:
        self.interaction.wait(seconds)

    def _checkpoint(self) -> None:
        self.interaction.checkpoint()

    def _configure(self, request: LightMeasurementRequest) -> None:
        self.lut_modes = set(request.modes)
        self.num_lights = request.multiple_light_count
        self.gzip = request.gzip
        self.light_info = self.light_controller.get_light_info()
        effects = self.light_controller.get_effect_list()
        self.plan = build_light_plan(self.lut_modes, self.config, self.light_info, effects)
        self.active_plan = None

    def writes_export_files(self) -> bool:
        return True

    def cleanup(self) -> None:
        try:
            self.light_controller.change_light_state(LutMode.BRIGHTNESS, on=False)
        except Exception as error:  # noqa: BLE001 - cleanup must not mask the measurement outcome
            _LOGGER.warning("Could not turn off the light during measurement cleanup: %s", error)
        else:
            _LOGGER.info("Turning off the light")
            self.interaction.operating_point(LightOperatingPoint(type="light", on=False))
        finally:
            try:
                self.light_controller.close()
            except Exception as error:  # noqa: BLE001 - cleanup must not mask the measurement outcome
                _LOGGER.warning("Could not close the light controller during measurement cleanup: %s", error)

    def run(self, request: LightMeasurementRequest, export_directory: str) -> RunnerResult:
        self._configure(request)
        assert self.plan is not None
        measurements_to_run = [
            self.prepare_measurements_for_mode(export_directory, mode_plan.mode) for mode_plan in self.plan.modes
        ]
        self.active_plan = LightMeasurementPlan(
            modes=[
                LightModePlan(mode=measurement.mode, variations=list(measurement.variations))
                for measurement in measurements_to_run
            ],
            effects=list(self.plan.effects),
        )

        progress = LightRunProgress(total=self.plan.variation_count, remaining=self.active_plan.variations.copy())
        _LOGGER.info("Total number of variations: %d", progress.total)
        voltages: list[float] = []

        for measurement_info in measurements_to_run:
            voltages.extend(self.run_mode(measurement_info, progress))

        if progress.remaining:
            raise RunnerError(f"Measurement ended with {len(progress.remaining)} incomplete variations")

        return RunnerResult(
            model_json_data={
                "device_type": "light",
                "calculation_strategy": "lut",
            },
            voltages=voltages,
        )

    def prepare_measurements_for_mode(self, export_directory: str, mode: LutMode) -> MeasurementRunInput:
        """Fetch all variations for the given color mode and prepare the measurement session."""

        if mode == LutMode.WHITE:
            mode = LutMode.BRIGHTNESS

        csv_file_path = f"{export_directory}/{mode.value}.csv"

        inspection = None
        if self.should_resume(csv_file_path):
            try:
                inspection = inspect_light_csv(
                    Path(csv_file_path), mode, include_datetime=self.config.csv_add_datetime_column
                )
            except ValueError as error:
                raise RunnerError(str(error)) from error

        assert self.plan is not None
        resume_at = inspection.last_complete_variation if inspection is not None else None
        variations = list(variations_after(self.plan.for_mode(mode).variations, resume_at))
        if inspection is not None:
            repair_incomplete_csv_tail(Path(csv_file_path), inspection)
        return MeasurementRunInput(
            mode=mode,
            csv_file=csv_file_path,
            variations=variations,
            is_resuming=bool(resume_at),
        )

    def _resolve_white_mode(self, mode: LutMode) -> LutMode:
        """WHITE is measured as BRIGHTNESS after turning the light fully on."""
        if mode == LutMode.WHITE:
            self.light_controller.change_light_state(mode, on=True, bri=255)
            return LutMode.BRIGHTNESS
        return mode

    def run_mode(
        self,
        measurement_info: MeasurementRunInput,
        progress: LightRunProgress,
    ) -> list[float]:
        """Measure and save each unfinished variation for one light mode."""

        mode = self._resolve_white_mode(measurement_info.mode)
        voltages: list[float] = []

        if measurement_info.is_resuming:
            _LOGGER.info("Resuming measurements")

        _LOGGER.info(
            "Starting measurements. Estimated duration: %s",
            self.calculate_time_left(mode, progress.remaining),
        )

        with open_csv_writer(
            Path(measurement_info.csv_file), mode, append=measurement_info.is_resuming, parameters=self.config
        ) as csv_writer:
            # Set maximum brightness twice to prevent some lights turning off
            # when starting at low brightness or after repeated off commands (#2598).
            assert self.light_info is not None
            set_light_to_maximum_brightness(
                self.light_controller,
                self.light_info,
                mode,
                sleep_time=self.config.sleep_time,
                wait=self._wait,
                checkpoint=self._checkpoint,
            )

            _LOGGER.info(
                "Start taking measurements for color mode: %s",
                mode.value,
            )

            self._report_progress(mode, progress)
            previous_variation = None
            for count, variation in enumerate(measurement_info.variations):
                self._log_progress(mode, count, variation, progress)
                result = self.measure_variation(mode, variation, previous_variation, progress)
                previous_variation = variation
                self._checkpoint()
                csv_writer.write_measurement(variation, result.power)
                voltages.extend(result.voltages)
                progress.remaining.remove(variation)
                self._report_progress(mode, progress, variation)

            _LOGGER.info(
                "Hooray! measurements finished. Exported CSV file %s",
                measurement_info.csv_file,
            )

        if self.gzip:
            compress_light_csv(Path(measurement_info.csv_file))
        return voltages

    def measure_variation(
        self,
        mode: LutMode,
        variation: Variation,
        previous_variation: Variation | None,
        progress: LightRunProgress,
    ) -> MeasurementResult:
        """Settle and measure one light setting, retrying zero or stale readings."""
        while True:
            _LOGGER.info("Changing light to: %s", variation)
            self._checkpoint()
            variation_start_time = time.time()
            self._change_light_with_retry(mode, variation)
            self.wait(variation, previous_variation)
            previous_variation = variation

            try:
                self._checkpoint()
                result = self.take_power_measurement(mode, variation_start_time)
            except OutdatedMeasurementError:
                result = self.nudge_and_remeasure(mode, variation)
            except ZeroReadingError as error:
                self._record_zero_reading()
                self._report_progress(mode, progress, variation)
                _LOGGER.warning("Discarding measurement: %s", error)
                self._raise_for_repeated_zero_readings(error)
                continue
            except PowerMeterError as error:
                raise RunnerError(f"Aborting measurement session: {error}") from error

            self.num_0_readings = 0
            _LOGGER.info("Measured power: %.2f", result.power)
            return result

    def _log_progress(
        self,
        mode: LutMode,
        count: int,
        variation: Variation,
        progress: LightRunProgress,
    ) -> None:
        if count % 10 != 0:
            return

        time_left = self.calculate_time_left(mode, progress.remaining, variation)
        progress_percentage = progress.completed / progress.total * 100
        _LOGGER.info("Progress: %d%%, Estimated time left: %s", progress_percentage, time_left)

    def _report_progress(
        self,
        mode: LutMode,
        progress: LightRunProgress,
        current_variation: Variation | None = None,
    ) -> None:
        self.interaction.progress(
            completed=progress.completed,
            total=progress.total,
            phase=mode.value,
            remaining_seconds=self.calculate_time_left_seconds(
                mode,
                progress.remaining,
                current_variation,
            ),
            skipped=self.skipped_zero_readings,
        )

    def _record_zero_reading(self) -> None:
        self.num_0_readings += 1
        self.skipped_zero_readings += 1

    def _raise_for_repeated_zero_readings(self, error: ZeroReadingError) -> None:
        if self.num_0_readings >= MAX_CONSECUTIVE_ZERO_READINGS:
            raise RunnerError(ZERO_READING_ABORT_MESSAGE) from error

    def _change_light_with_retry(self, mode: LutMode, variation: Variation) -> None:
        for _ in range(5):
            try:
                self._checkpoint()
                self.light_controller.change_light_state(
                    mode,
                    on=True,
                    **asdict(variation),
                )
                self.interaction.operating_point(self._build_operating_point(mode, variation))
                return
            except ApiConnectionError as error:
                _LOGGER.warning("Failed to change light state: %s. Retrying...", error)
                self._wait(5)
        raise RunnerError("Failed to change light state after 5 retries")

    def wait(self, variation: Variation, previous_variation: Variation | None) -> None:
        """Wait for the light to process the change"""
        self._wait(self.config.sleep_time)

        if not previous_variation:
            # Initially wait longer after selecting the first measurement point so
            # the smart plug cannot report a reading left over from maximum load.
            _LOGGER.info("Waiting %d seconds...", self.config.sleep_initial)
            self.interaction.phase(f"Stabilizing light before the first reading ({self.config.sleep_initial} s)")
            self._wait(self.config.sleep_initial)
            return

        if (
            isinstance(variation, ColorTempVariation)
            and isinstance(previous_variation, ColorTempVariation)
            and variation.ct < previous_variation.ct
        ):
            _LOGGER.info("Extra waiting for significant CT change...")
            self._wait(self.config.sleep_time_ct)
            return

        if isinstance(variation, HsVariation) and isinstance(previous_variation, HsVariation):
            if variation.hue < previous_variation.hue:
                _LOGGER.info("Extra waiting for significant HUE change...")
                self._wait(self.config.sleep_time_hue)
            if variation.sat < previous_variation.sat:
                _LOGGER.info("Extra waiting for significant SAT change...")
                self._wait(self.config.sleep_time_sat)
            return

        if (
            isinstance(variation, EffectVariation)
            and isinstance(previous_variation, EffectVariation)
            and variation.is_effect_changed(previous_variation)
        ):
            _LOGGER.info("Extra waiting for effect change...")
            self._wait(self.config.sleep_time_effect_change)

    def calculate_time_left(
        self,
        current_mode: LutMode,
        remaining_variations: list[Variation],
        current_variation: Variation | None = None,
    ) -> str:
        """Try to guess the remaining time left. This will not account for measuring errors / retries obviously"""
        return self.format_time_left(
            self.calculate_time_left_seconds(
                current_mode,
                remaining_variations,
                current_variation,
            ),
        )

    def calculate_time_left_seconds(
        self,
        current_mode: LutMode,
        remaining_variations: list[Variation],
        current_variation: Variation | None = None,
    ) -> float:
        """Return the shared remaining-time estimate for progress consumers."""
        assert self.active_plan is not None
        return estimate_light_time_left(
            self.active_plan,
            self.config,
            current_mode=current_mode,
            remaining_variations=remaining_variations,
            current_variation=current_variation,
        )

    @staticmethod
    def format_time_left(time_left: float) -> str:
        """Format the time left in a human readable format"""
        if time_left < 0:
            time_left = 0
        if time_left > 3600:
            formatted_time = f"{round(time_left / 3600, 1)}h"
        elif time_left > 60:
            formatted_time = f"{round(time_left / 60, 1)}m"
        else:
            formatted_time = f"{round(time_left, 1)}s"

        return formatted_time

    def nudge_and_remeasure(
        self,
        mode: LutMode,
        variation: Variation,
    ) -> MeasurementResult:
        if self.config.max_nudges == 0:
            raise OutdatedMeasurementError(
                "Power measurement is outdated and nudging is disabled (max_nudges=0)",
            )
        for _ in range(self.config.max_nudges):
            try:
                # Likely not significant enough change for PM to detect. Try nudging it
                _LOGGER.warning("Measurement is stuck, Nudging")
                # If brightness is low, set brightness high. Else, turn light off
                self._checkpoint()
                self.light_controller.change_light_state(
                    LutMode.BRIGHTNESS,
                    on=(variation.bri < 128),
                    bri=255,
                )
                self._wait(self.config.pulse_time_nudge)
                variation_start_time = time.time()
                self._checkpoint()
                self.light_controller.change_light_state(
                    mode,
                    on=True,
                    **asdict(variation),
                )
                self.interaction.operating_point(self._build_operating_point(mode, variation))
                # Wait a longer amount of time for the PM to settle
                self._wait(self.config.sleep_time_nudge)
                result = self.take_power_measurement(mode, variation_start_time)
                self.num_0_readings = 0
                return result
            except OutdatedMeasurementError:
                continue
            except ZeroReadingError as error:
                self._record_zero_reading()
                _LOGGER.warning("Discarding measurement: %s", error)
                self._raise_for_repeated_zero_readings(error)
                continue
        raise OutdatedMeasurementError(
            f"Power measurement is outdated. Aborting after {self.config.max_nudges} nudge attempts",
        )

    def should_resume(self, csv_file_path: str) -> bool:
        """Apply the configured resume policy to a non-empty measurement CSV."""
        if not self._resume or not has_measurement_rows(Path(csv_file_path)):
            return False
        if not self.config.prompt_resume:
            return True
        return self.interaction.choose(
            f"CSV File {csv_file_path} already exists. Do you want to resume measurements?",
            default=True,
        )

    def take_power_measurement(
        self,
        mode: LutMode,
        start_timestamp: float,
        retry_count: int = 0,
    ) -> MeasurementResult:
        """Take an effect average or a timestamp-validated point reading."""
        if mode == LutMode.EFFECT:
            result = self.sampler.take_average_measurement(
                self.config.measure_time_effect,
                convergence=AverageMeasurementConvergence(
                    min_duration=self.config.measure_time_effect_min,
                    window_duration=self.config.measure_time_effect_convergence_window,
                    absolute_threshold=self.config.measure_time_effect_convergence_abs,
                    relative_threshold=self.config.measure_time_effect_convergence_rel,
                ),
            )
        else:
            result = self.sampler.take_measurement(start_timestamp, retry_count)

        # Determine per load power consumption
        power = result.power / self.num_lights

        return MeasurementResult(power=round(power, 2), voltages=result.voltages)

    def measure_standby_power(self) -> MeasurementResult:
        """Measures the standby power (when the light is OFF)"""
        self._checkpoint()
        self.light_controller.change_light_state(LutMode.BRIGHTNESS, on=False)
        self.interaction.operating_point(LightOperatingPoint(type="light", on=False))
        start_time = time.time()
        _LOGGER.info(
            "Measuring standby power. Waiting for %d seconds...",
            self.config.sleep_standby,
        )
        self._wait(self.config.sleep_standby)
        try:
            self._checkpoint()
            return self.take_power_measurement(LutMode.BRIGHTNESS, start_time)
        except OutdatedMeasurementError:
            return self.nudge_and_remeasure(LutMode.BRIGHTNESS, Variation(0))
        except ZeroReadingError:
            _LOGGER.error(
                "Measured 0 watt as standby usage, continuing now, "
                "but you probably need to have a look into measuring multiple lights at the same time "
                "or using a dummy load.",
            )
            return MeasurementResult(power=0, voltages=[])

    @staticmethod
    def _build_operating_point(mode: LutMode, variation: Variation) -> LightOperatingPoint:
        point = LightOperatingPoint(type="light", on=True, brightness=variation.bri)
        if mode == LutMode.COLOR_TEMP and isinstance(variation, ColorTempVariation):
            point["color_temp_mired"] = variation.ct
        elif mode == LutMode.HS and isinstance(variation, HsVariation):
            point["hue"] = variation.hue
            point["saturation"] = variation.sat
        elif mode == LutMode.EFFECT and isinstance(variation, EffectVariation):
            point["effect"] = variation.effect
        return point


@dataclass(frozen=True)
class MeasurementRunInput:
    mode: LutMode
    csv_file: str
    variations: list[Variation]
    is_resuming: bool
