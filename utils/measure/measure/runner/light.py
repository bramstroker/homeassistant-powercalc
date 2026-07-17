from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime as dt
import gzip
import logging
import os
import shutil
import time
from typing import Literal, TextIO

from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.controller.light.errors import ApiConnectionError
from measure.execution import ImmediateInteraction, LightOperatingPoint, RunInteraction
from measure.powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)
from measure.request import LightMeasurementRequest
from measure.runner.errors import RunnerError
from measure.runner.light_plan import (
    CSV_HEADERS,
    ColorTempVariation,
    EffectVariation,
    HsVariation,
    LightMeasurementPlan,
    LightModePlan,
    Variation,
    build_light_plan,
    estimate_light_time_left,
    variation_from_csv_row,
    variations_after,
)
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.tuning import MeasurementParameters
from measure.util.measure_util import AverageMeasurementConvergence, MeasurementResult, MeasureUtil

CSV_WRITE_BUFFER = 50
MAX_ALLOWED_0_READINGS = 50

_LOGGER = logging.getLogger("measure")


class LightRunner(MeasurementRunner[LightMeasurementRequest]):
    """Measure configured light modes and write one LUT CSV per mode."""

    def __init__(
        self,
        measure_util: MeasureUtil,
        parameters: MeasurementParameters,
        light_controller: LightController,
        interaction: RunInteraction | None = None,
        *,
        resume: bool = False,
    ) -> None:
        self.light_controller = light_controller
        self.measure_util = measure_util
        self.lut_modes: set[LutMode] | None = None
        self.num_lights: int = 1
        self.num_0_readings: int = 0
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

        all_variations: list[Variation] = []
        for measurement in measurements_to_run:
            all_variations.extend(measurement.variations)
        _LOGGER.info("Total number of variations: %d", len(all_variations))
        remaining_variations = all_variations.copy()
        voltages: list[float] = []

        for measurement_info in measurements_to_run:
            voltages.extend(self.run_mode(measurement_info, all_variations, remaining_variations))

        if remaining_variations:
            raise RunnerError(f"Measurement ended with {len(remaining_variations)} incomplete variations")

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

        resume_at = None
        if self.should_resume(csv_file_path):
            resume_at = self.get_resume_variation(csv_file_path, mode)

        assert self.plan is not None
        variations = list(variations_after(self.plan.for_mode(mode).variations, resume_at))
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
        all_variations: list[Variation],
        remaining_variations: list[Variation],
    ) -> list[float]:
        """Run the measurement session for lights"""

        mode = self._resolve_white_mode(measurement_info.mode)
        voltages: list[float] = []

        file_write_mode, write_header_row = self._get_csv_write_options(measurement_info)

        _LOGGER.info(
            "Starting measurements. Estimated duration: %s",
            self.calculate_time_left(mode, all_variations, remaining_variations),
        )

        with open(measurement_info.csv_file, file_write_mode, newline="") as csv_file:
            csv_writer = CsvWriter(csv_file, mode, write_header_row, self.config)

            # To avoid bugs in some lights, when set to low brightness initially
            # where they turn off again. And also bugs where lights will turn off
            # again, after they received two turn-off commands, followed by a single
            # turn on command, we set them to maximum brightness, twice here.
            # See issue #2598
            self.set_light_to_maximum_brightness(mode)

            # Initially wait longer so the smartplug can settle
            _LOGGER.info(
                "Start taking measurements for color mode: %s",
                mode.value,
            )
            _LOGGER.info("Waiting %d seconds...", self.config.sleep_initial)
            self.interaction.phase(f"Stabilizing light before the first reading ({self.config.sleep_initial} s)")
            self._wait(self.config.sleep_initial)

            self.interaction.progress(
                completed=len(all_variations) - len(remaining_variations),
                total=len(all_variations),
                phase=mode.value,
                remaining_seconds=self.calculate_time_left_seconds(mode, all_variations, remaining_variations),
            )
            previous_variation = None
            for count, variation in enumerate(measurement_info.variations):
                self._log_progress(mode, count, variation, all_variations, remaining_variations)
                _LOGGER.info("Changing light to: %s", variation)
                self._checkpoint()
                variation_start_time = time.time()
                self._change_light_with_retry(mode, variation)
                self.wait(variation, previous_variation)

                previous_variation = variation

                try:
                    self._checkpoint()
                    measurement_result = self.take_power_measurement(mode, variation_start_time)
                except OutdatedMeasurementError:
                    measurement_result = self.nudge_and_remeasure(mode, variation)
                except ZeroReadingError as error:
                    self.num_0_readings += 1
                    _LOGGER.warning("Discarding measurement: %s", error)
                    if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                        raise RunnerError(
                            "Aborting measurement session. Received too many 0 readings",
                        ) from error
                    continue
                except PowerMeterError as error:
                    raise RunnerError(f"Aborting measurement session: {error}") from error
                _LOGGER.info("Measured power: %.2f", measurement_result.power)
                self._checkpoint()
                csv_writer.write_measurement(variation, measurement_result.power)
                voltages.extend(measurement_result.voltages)
                remaining_variations.remove(variation)
                self.interaction.progress(
                    completed=len(all_variations) - len(remaining_variations),
                    total=len(all_variations),
                    phase=mode.value,
                    remaining_seconds=self.calculate_time_left_seconds(
                        mode,
                        all_variations,
                        remaining_variations,
                        variation,
                    ),
                )

            _LOGGER.info(
                "Hooray! measurements finished. Exported CSV file %s",
                measurement_info.csv_file,
            )

        if self.gzip:
            self.gzip_csv(measurement_info.csv_file)
        return voltages

    def _get_csv_write_options(self, measurement_info: MeasurementRunInput) -> tuple[Literal["w", "a"], bool]:
        if not measurement_info.is_resuming:
            return "w", True

        _LOGGER.info("Resuming measurements")
        return "a", False

    def _log_progress(
        self,
        mode: LutMode,
        count: int,
        variation: Variation,
        all_variations: list[Variation],
        remaining_variations: list[Variation],
    ) -> None:
        if count % 10 != 0:
            return

        time_left = self.calculate_time_left(mode, all_variations, remaining_variations, variation)
        progress_percentage = ((len(all_variations) - len(remaining_variations)) / len(all_variations)) * 100
        _LOGGER.info("Progress: %d%%, Estimated time left: %s", progress_percentage, time_left)

    def _change_light_with_retry(self, mode: LutMode, variation: Variation) -> None:
        for _ in range(5):
            try:
                self._checkpoint()
                self.light_controller.change_light_state(
                    mode,
                    on=True,
                    **asdict(variation),
                )
                self.interaction.operating_point(self._operating_point(mode, variation))
                return
            except ApiConnectionError as error:
                _LOGGER.warning("Failed to change light state: %s. Retrying...", error)
                self._wait(5)
        raise RunnerError("Failed to change light state after 5 retries")

    def wait(self, variation: Variation, previous_variation: Variation | None) -> None:
        """Wait for the light to process the change"""
        self._wait(self.config.sleep_time)

        if not previous_variation:
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

    def set_light_to_maximum_brightness(self, mode: LutMode) -> None:
        """Set maximum brightness twice for lights that turn off after rapid commands."""
        assert self.light_info is not None
        _LOGGER.info("Turning on light with maximum brightness")
        # Turn the light on twice to ensure it's in the correct state
        for _ in range(2):
            self._checkpoint()
            if mode == LutMode.HS:
                self.light_controller.change_light_state(
                    mode,
                    on=True,
                    bri=255,
                    hue=0,  # Set default hue
                    sat=1,  # Set default saturation
                )
            elif mode == LutMode.COLOR_TEMP:
                self.light_controller.change_light_state(
                    mode,
                    on=True,
                    bri=255,
                    ct=self.light_info.min_mired,  # Set to minimum mired value for color temp
                )
            else:
                self.light_controller.change_light_state(
                    LutMode.BRIGHTNESS,
                    on=True,
                    bri=255,
                )
            self._wait(self.config.sleep_time)  # Wait for the light to process

    def calculate_time_left(
        self,
        current_mode: LutMode,
        all_variations: list[Variation],
        remaining_variations: list[Variation],
        current_variation: Variation | None = None,
    ) -> str:
        """Try to guess the remaining time left. This will not account for measuring errors / retries obviously"""
        return self.format_time_left(
            self.calculate_time_left_seconds(
                current_mode,
                all_variations,
                remaining_variations,
                current_variation,
            ),
        )

    def calculate_time_left_seconds(
        self,
        current_mode: LutMode,
        all_variations: list[Variation],
        remaining_variations: list[Variation],
        current_variation: Variation | None = None,
    ) -> float:
        """Return the shared remaining-time estimate for progress consumers."""
        assert self.active_plan is not None
        assert all_variations == self.active_plan.variations
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
                self.interaction.operating_point(self._operating_point(mode, variation))
                # Wait a longer amount of time for the PM to settle
                self._wait(self.config.sleep_time_nudge)
                return self.take_power_measurement(mode, variation_start_time)
            except OutdatedMeasurementError:
                continue
            except ZeroReadingError as error:
                self.num_0_readings += 1
                _LOGGER.warning("Discarding measurement: %s", error)
                if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                    raise RunnerError(
                        "Aborting measurement session. Received too many 0 readings",
                    ) from error
                continue
        raise OutdatedMeasurementError(
            f"Power measurement is outdated. Aborting after {self.config.max_nudges} nudge attempts",
        )

    def should_resume(self, csv_file_path: str) -> bool:
        """Apply the configured resume policy to a non-empty measurement CSV."""
        if not os.path.exists(csv_file_path):
            return False

        size = os.path.getsize(csv_file_path)
        if size == 0:
            return False

        with open(csv_file_path) as csv_file:
            rows = csv.reader(csv_file)
            if len(list(rows)) == 1:
                return False

        should_resume = self._resume
        if should_resume:
            if not self.config.prompt_resume:
                return True
            return self.interaction.choose(
                f"CSV File {csv_file_path} already exists. Do you want to resume measurements?",
                default=True,
            )
        return should_resume

    def get_resume_variation(self, csv_file_path: str, mode: LutMode) -> Variation | None:
        """Parse the last complete CSV row into the variation from which the mode resumes.

        Trailing rows that cannot be parsed (typically a torn final line after a crash)
        are dropped from the file so appended measurements produce a valid CSV.
        """

        with open(csv_file_path, newline="") as csv_file:
            rows = list(csv.reader(csv_file))

        valid_row_count = len(rows)
        while valid_row_count > 1 and variation_from_csv_row(rows[valid_row_count - 1], mode) is None:
            valid_row_count -= 1

        if valid_row_count < len(rows):
            _LOGGER.warning(
                "Dropping %d incomplete trailing row(s) from %s before resuming",
                len(rows) - valid_row_count,
                csv_file_path,
            )
            with open(csv_file_path, "w", newline="") as csv_file:
                csv.writer(csv_file).writerows(rows[:valid_row_count])

        if valid_row_count == 1:
            return None
        return variation_from_csv_row(rows[valid_row_count - 1], mode)

    def take_power_measurement(
        self,
        mode: LutMode,
        start_timestamp: float,
        retry_count: int = 0,
    ) -> MeasurementResult:
        """Take an effect average or a timestamp-validated point reading."""
        if mode == LutMode.EFFECT:
            result = self.measure_util.take_average_measurement(
                self.config.measure_time_effect,
                convergence=AverageMeasurementConvergence(
                    min_duration=self.config.measure_time_effect_min,
                    window_duration=self.config.measure_time_effect_convergence_window,
                    absolute_threshold=self.config.measure_time_effect_convergence_abs,
                    relative_threshold=self.config.measure_time_effect_convergence_rel,
                ),
            )
        else:
            result = self.measure_util.take_measurement(start_timestamp, retry_count)

        # Determine per load power consumption
        power = result.power / self.num_lights

        return MeasurementResult(power=round(power, 2), voltages=result.voltages)

    @staticmethod
    def gzip_csv(csv_file_path: str) -> None:
        """Gzip the CSV file"""
        with (
            open(csv_file_path, "rb") as csv_file,
            gzip.open(
                f"{csv_file_path}.gz",
                "wb",
            ) as gzip_file,
        ):
            shutil.copyfileobj(csv_file, gzip_file)

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
    def _operating_point(mode: LutMode, variation: Variation) -> LightOperatingPoint:
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


class CsvWriter:
    def __init__(
        self,
        csv_file: TextIO,
        mode: LutMode,
        add_header: bool,
        parameters: MeasurementParameters,
    ) -> None:
        self.csv_file = csv_file
        self.config = parameters
        self.writer = csv.writer(csv_file)
        self.rows_written = 0
        if add_header:
            header_row = [*CSV_HEADERS[mode]]
            if self.config.csv_add_datetime_column:
                header_row.append("time")
            self.writer.writerow(header_row)

    def write_measurement(self, variation: Variation, power: float) -> None:
        """Write row with measurement to the CSV"""
        row = variation.to_csv_row()
        row.append(power)
        if self.config.csv_add_datetime_column:
            row.append(dt.now().strftime("%Y%m%d%H%M%S"))
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % CSV_WRITE_BUFFER == 1:
            self.csv_file.flush()
            _LOGGER.debug("Flushing CSV buffer")
