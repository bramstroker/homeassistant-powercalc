from __future__ import annotations

import csv
import gzip
import logging
import os
import re
import shutil
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime as dt
from pathlib import Path
from typing import Any, TextIO

import config
import inquirer
from light_controller.const import ColorMode
from light_controller.controller import LightInfo
from light_controller.factory import LightControllerFactory
from measure_util import MeasureUtil
from powermeter.errors import (
    OutdatedMeasurementError,
    PowerMeterError,
    ZeroReadingError,
)

from .runner import MeasurementRunner, RunnerResult

CSV_HEADERS = {
    ColorMode.HS: ["bri", "hue", "sat", "watt"],
    ColorMode.COLOR_TEMP: ["bri", "mired", "watt"],
    ColorMode.BRIGHTNESS: ["bri", "watt"],
}

CSV_WRITE_BUFFER = 50
MAX_ALLOWED_0_READINGS = 50

_LOGGER = logging.getLogger("measure")


class LightRunner(MeasurementRunner):
    """
    This class is responsible for measuring the power usage of a light. It uses a LightController to control the light, and a PowerMeter
    to measure the power usage. The measurements are exported as CSV files in export/<model_id>/<color_mode>.csv (or .csv.gz). The
    model_id is retrieved from the LightController and color mode can be selected by user input or config file (.env). The CSV files
    contain one row per variation, where each column represents one property of that variation (e.g., brightness, hue, saturation). The last
    column contains the measured power value in watt.
    If you want to generate model JSON files for the LUT model, you can do so by answering yes to the question "Do you want to generate
    model.json?".

    # CSV file export/<model-id>/hs.csv will be created with measurements for HS
    color mode (e.g., hue and saturation). The last column contains the measured
    power value in watt.
    """

    def __init__(self, measure_util: MeasureUtil) -> None:
        self.light_controller = LightControllerFactory().create()
        self.measure_util = measure_util
        self.color_mode: ColorMode | None = None
        self.num_lights: int = 1
        self.is_dummy_load_connected: bool = False
        self.dummy_load_value: float = 0
        self.num_0_readings: int = 0
        self.light_info: LightInfo | None = None

    def prepare(self, answers: dict[str, Any]) -> None:
        self.light_controller.process_answers(answers)
        self.color_mode = answers["color_mode"]
        self.num_lights = int(answers.get("num_lights") or 1)
        self.is_dummy_load_connected = bool(answers.get("dummy_load"))
        if self.is_dummy_load_connected:
            self.dummy_load_value = self.get_dummy_load_value()
            _LOGGER.info(f"Using {self.dummy_load_value}W as dummy load value")

        self.light_info = self.light_controller.get_light_info()

    def get_export_directory(self) -> str:
        return f"{self.light_info.model_id}"

    def run(
        self,
        answers: dict[str, Any],
        export_directory: str,
    ) -> RunnerResult | None:
        """Run the measurement session for lights"""
        csv_file_path = f"{export_directory}/{self.color_mode}.csv"

        resume_at = None
        file_write_mode = "w"
        write_header_row = True
        if self.should_resume(csv_file_path):
            _LOGGER.info("Resuming measurements")
            resume_at = self.get_resume_variation(csv_file_path)
            file_write_mode = "a"
            write_header_row = False

        variations = list(self.get_variations(self.color_mode, resume_at))
        num_variations = len(variations)

        _LOGGER.info(
            f"Starting measurements. Estimated duration: {self.calculate_time_left(variations, variations[0])}",
        )

        with open(csv_file_path, file_write_mode, newline="") as csv_file:
            csv_writer = CsvWriter(csv_file, self.color_mode, write_header_row)

            if resume_at is None:
                self.light_controller.change_light_state(
                    ColorMode.BRIGHTNESS,
                    on=True,
                    bri=1,
                )

            # Initially wait longer so the smartplug can settle
            _LOGGER.info(f"Start taking measurements for color mode: {self.color_mode}")
            _LOGGER.info(f"Waiting {config.SLEEP_INITIAL} seconds...")
            time.sleep(config.SLEEP_INITIAL)

            previous_variation = None
            for count, variation in enumerate(variations):
                if count % 10 == 0:
                    time_left = self.calculate_time_left(variations, variation, count)
                    progress_percentage = round(count / num_variations * 100)
                    _LOGGER.info(
                        f"Progress: {progress_percentage}%, Estimated time left: {time_left}",
                    )
                _LOGGER.info(f"Changing light to: {variation}")
                variation_start_time = time.time()
                self.light_controller.change_light_state(
                    self.color_mode,
                    on=True,
                    **asdict(variation),
                )

                if (
                    previous_variation
                    and isinstance(variation, ColorTempVariation)
                    and variation.ct < previous_variation.ct
                ):
                    _LOGGER.info("Extra waiting for significant CT change...")
                    time.sleep(config.SLEEP_TIME_CT)

                if (
                    previous_variation
                    and isinstance(variation, HsVariation)
                    and variation.sat < previous_variation.sat
                ):
                    _LOGGER.info("Extra waiting for significant SAT change...")
                    time.sleep(config.SLEEP_TIME_SAT)

                if (
                    previous_variation
                    and isinstance(variation, HsVariation)
                    and variation.hue < previous_variation.hue
                ):
                    _LOGGER.info("Extra waiting for significant HUE change...")
                    time.sleep(config.SLEEP_TIME_HUE)

                previous_variation = variation
                time.sleep(config.SLEEP_TIME)
                try:
                    power = self.take_power_measurement(variation_start_time)
                except OutdatedMeasurementError:
                    power = self.nudge_and_remeasure(self.color_mode, variation)
                except ZeroReadingError as error:
                    self.num_0_readings += 1
                    _LOGGER.warning(f"Discarding measurement: {error}")
                    if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                        _LOGGER.error(
                            "Aborting measurement session. Received too many 0 readings",
                        )
                        return None
                    continue
                except PowerMeterError as error:
                    _LOGGER.error(f"Aborting: {error}")
                    return None
                _LOGGER.info(f"Measured power: {power}")
                csv_writer.write_measurement(variation, power)

            csv_file.close()
            _LOGGER.info(
                f"Hooray! measurements finished. Exported CSV file {csv_file_path}",
            )

            self.light_controller.change_light_state(ColorMode.BRIGHTNESS, on=False)
            _LOGGER.info("Turning off the light")

        if bool(answers.get("gzip", True)):
            self.gzip_csv(csv_file_path)

        return RunnerResult(
            model_json_data={"calculation_strategy": "lut"},
        )

    def get_dummy_load_value(self) -> float:
        """Get the previously measured dummy load value"""

        dummy_load_file = os.path.join(
            Path(__file__).parent.parent.absolute(),
            ".persistent/dummy_load",
        )
        if not os.path.exists(dummy_load_file):
            return self.measure_dummy_load(dummy_load_file)

        with open(dummy_load_file) as f:
            return float(f.read())

    def measure_dummy_load(self, file_path: str) -> float:
        """Measure the dummy load and persist the value for future measurement session"""
        input(
            "Only connect your dummy load to your smart plug, not the light! Press enter to start measuring the dummy load..",
        )
        average = self.measure_util.take_average_measurement(30)
        with open(file_path, "w") as f:
            f.write(str(average))

        input("Connect your light now and press enter to start measuring..")
        return average

    def get_variations(
        self,
        color_mode: ColorMode,
        resume_at: Variation | None = None,
    ) -> Iterator[Variation]:
        """Get all the light settings where the measure script needs to cycle through"""
        if color_mode == ColorMode.HS:
            variations = self.get_hs_variations()
        elif color_mode == ColorMode.COLOR_TEMP:
            variations = self.get_ct_variations()
        else:
            variations = self.get_brightness_variations()

        if resume_at:
            include_variation = False
            for variation in variations:
                if include_variation:
                    yield variation

                # Current variation is the one we need to resume at.
                # Set include_variation flag so it every variation from now on will be yielded next iteration
                if variation == resume_at:
                    include_variation = True
        else:
            yield from variations

    def get_ct_variations(self) -> Iterator[ColorTempVariation]:
        """Get color_temp variations"""
        min_mired = round(self.light_info.min_mired)
        max_mired = round(self.light_info.max_mired)
        for bri in self.inclusive_range(
            config.MIN_BRIGHTNESS,
            config.MAX_BRIGHTNESS,
            config.CT_BRI_STEPS,
        ):
            for mired in self.inclusive_range(
                min_mired,
                max_mired,
                config.CT_MIRED_STEPS,
            ):
                yield ColorTempVariation(bri=bri, ct=mired)

    def get_hs_variations(self) -> Iterator[HsVariation]:
        """Get hue/sat variations"""
        for bri in self.inclusive_range(
            config.MIN_BRIGHTNESS,
            config.MAX_BRIGHTNESS,
            config.HS_BRI_STEPS,
        ):
            for sat in self.inclusive_range(
                config.MIN_SAT,
                config.MAX_SAT,
                config.HS_SAT_STEPS,
            ):
                for hue in self.inclusive_range(
                    config.MIN_HUE,
                    config.MAX_HUE,
                    config.HS_HUE_STEPS,
                ):
                    yield HsVariation(bri=bri, hue=hue, sat=sat)

    def get_brightness_variations(self) -> Iterator[Variation]:
        """Get brightness variations"""
        for bri in self.inclusive_range(
            config.MIN_BRIGHTNESS,
            config.MAX_BRIGHTNESS,
            config.BRI_BRI_STEPS,
        ):
            yield Variation(bri=bri)

    @staticmethod
    def inclusive_range(start: int, end: int, step: int) -> Iterator[int]:
        """Get an iterator including the min and max, with steps in between"""
        i = start
        while i < end:
            yield i
            i += step
        yield end

    @staticmethod
    def calculate_time_left(
        variations: list[Variation],
        current_variation: Variation = None,
        progress: int = 0,
    ) -> str:
        """Try to guess the remaining time left. This will not account for measuring errors / retries obviously"""
        num_variations_left = len(variations) - progress

        # Account estimated seconds for the light_controller and power_meter to process
        estimated_step_delay = 0.15

        time_left = 0
        if progress == 0:
            time_left += config.SLEEP_STANDBY + config.SLEEP_INITIAL
        time_left += num_variations_left * (config.SLEEP_TIME + estimated_step_delay)
        if config.SAMPLE_COUNT > 1:
            time_left += (
                num_variations_left
                * config.SAMPLE_COUNT
                * (config.SLEEP_TIME_SAMPLE + estimated_step_delay)
            )

        if isinstance(current_variation, HsVariation):
            sat_steps_left = (
                round(
                    (config.MAX_BRIGHTNESS - current_variation.bri)
                    / config.HS_BRI_STEPS,
                )
                - 1
            )
            time_left += sat_steps_left * config.SLEEP_TIME_SAT
            hue_steps_left = round(
                config.MAX_HUE / config.HS_HUE_STEPS * sat_steps_left,
            )
            time_left += hue_steps_left * config.SLEEP_TIME_HUE

        if isinstance(current_variation, ColorTempVariation):
            ct_steps_left = (
                round(
                    (config.MAX_BRIGHTNESS - current_variation.bri)
                    / config.CT_BRI_STEPS,
                )
                - 1
            )
            time_left += ct_steps_left * config.SLEEP_TIME_CT

        if time_left > 3600:
            formatted_time = f"{round(time_left / 3600, 1)}h"
        elif time_left > 60:
            formatted_time = f"{round(time_left / 60, 1)}m"
        else:
            formatted_time = f"{time_left}s"

        return formatted_time

    def nudge_and_remeasure(
        self, color_mode: str, variation: Variation,
    ) -> float | None:
        nudge_count = 0
        for nudge_count in range(config.MAX_NUDGES):  # noqa: B007
            try:
                # Likely not significant enough change for PM to detect. Try nudging it
                _LOGGER.warning("Measurement is stuck, Nudging")
                # If brightness is low, set brightness high. Else, turn light off
                self.light_controller.change_light_state(
                    ColorMode.BRIGHTNESS,
                    on=(variation.bri < 128),
                    bri=255,
                )
                time.sleep(config.PULSE_TIME_NUDGE)
                variation_start_time = time.time()
                self.light_controller.change_light_state(
                    color_mode,
                    on=True,
                    **asdict(variation),
                )
                # Wait a longer amount of time for the PM to settle
                time.sleep(config.SLEEP_TIME_NUDGE)
                power = self.take_power_measurement(variation_start_time)
                return power
            except OutdatedMeasurementError:
                continue
            except ZeroReadingError as error:
                self.num_0_readings += 1
                _LOGGER.warning(f"Discarding measurement: {error}")
                if self.num_0_readings > MAX_ALLOWED_0_READINGS:
                    _LOGGER.error(
                        "Aborting measurement session. Received too many 0 readings",
                    )
                    return None
                continue
        raise OutdatedMeasurementError(
            f"Power measurement is outdated. Aborting after {nudge_count + 1} nudged retries",
        )

    @staticmethod
    def should_resume(csv_file_path: str) -> bool:
        """This method checks if a CSV file already exists for the current color mode.

        If so, it asks the user if he wants to resume measurements or start over.

        Parameters
        ----------
        csv_file_path : str
            The path of the CSV file that should be checked

        Returns
        -------
        bool
            True if we should resume measurements, False otherwise.

        Raises
        ------
        Exception
            When something goes wrong with reading/writing files.

        UndefinedValueError
            When no value is defined in .env for RESUME key.

        ValueError
            When an invalid value is defined in .env for RESUME key (not 'true' or 'false').

        """
        if not os.path.exists(csv_file_path):
            return False

        size = os.path.getsize(csv_file_path)
        if size == 0:
            return False

        with open(csv_file_path) as csv_file:
            rows = csv.reader(csv_file)
            if len(list(rows)) == 1:
                return False

        should_resume = config.RESUME
        if should_resume is None:
            return inquirer.confirm(
                message="CSV File already exists. Do you want to resume measurements?",
                default=True,
            )
        return should_resume

    def get_resume_variation(self, csv_file_path: str) -> Variation | None:
        """This method returns the variation to resume at.

        It reads the last row from the CSV file and converts it into a Variation object.

        Parameters
        ----------
        csv_file_path : str
            The path to the CSV file

        Returns
        -------
        Variation:
            The variation to resume at. None if no resuming is needed.

        Raises
        -------
        FileNotFoundError, Exception, ZeroDivisionError, ValueError, TypeError, IndexError

        Examples
        --------
        >>> get_resume_variation("/home/user/export/LCT001/hs.csv") -> HsVariation(bri=254, hue=0, sat=0)

        See Also
        -------
        get_variations()

        Notes
        -------
        This method will raise an exception when something goes wrong while reading or parsing the CSV file or when an unsupported color
        mode is used in the CSV file.
        """

        with open(csv_file_path) as csv_file:
            rows = csv.reader(csv_file)
            last_row = list(rows)[-1]

        if self.color_mode == ColorMode.BRIGHTNESS:
            return Variation(bri=int(last_row[0]))

        if self.color_mode == ColorMode.COLOR_TEMP:
            return ColorTempVariation(bri=int(last_row[0]), ct=int(last_row[1]))

        if self.color_mode == ColorMode.HS:
            return HsVariation(
                bri=int(last_row[0]),
                hue=int(last_row[1]),
                sat=int(last_row[2]),
            )

        raise Exception(f"Color mode {self.color_mode} not supported")

    def take_power_measurement(
        self,
        start_timestamp: float,
        retry_count: int = 0,
    ) -> float:
        """Request a power reading from the configured power meter"""
        value = self.measure_util.take_measurement(start_timestamp, retry_count)

        # Subtract Dummy Load (if present)
        if self.is_dummy_load_connected:
            value -= self.dummy_load_value

        # Determine per load power consumption
        value /= self.num_lights

        return round(value, 2)

    @staticmethod
    def gzip_csv(csv_file_path: str) -> None:
        """Gzip the CSV file"""
        with open(csv_file_path, "rb") as csv_file, gzip.open(
            f"{csv_file_path}.gz",
            "wb",
        ) as gzip_file:
            shutil.copyfileobj(csv_file, gzip_file)

    def measure_standby_power(self) -> float:
        """Measures the standby power (when the light is OFF)"""
        self.light_controller.change_light_state(ColorMode.BRIGHTNESS, on=False)
        start_time = time.time()
        _LOGGER.info(
            f"Measuring standby power. Waiting for {config.SLEEP_STANDBY} seconds...",
        )
        time.sleep(config.SLEEP_STANDBY)
        try:
            return self.take_power_measurement(start_time)
        except OutdatedMeasurementError:
            self.nudge_and_remeasure(ColorMode.BRIGHTNESS, Variation(0))
        except ZeroReadingError:
            _LOGGER.error(
                "Measured 0 watt as standby usage, continuing now, "
                "but you probably need to have a look into measuring multiple lights at the same time "
                "or using a dummy load.",
            )
            return 0

    def get_questions(self) -> list[inquirer.questions.Question]:
        """Get questions to ask for the light runner"""
        questions = [
            inquirer.List(
                name="color_mode",
                message="Select the color mode",
                choices=[ColorMode.HS, ColorMode.COLOR_TEMP, ColorMode.BRIGHTNESS],
                default=ColorMode.HS,
            ),
            inquirer.Confirm(
                name="gzip",
                message="Do you want to gzip CSV files?",
                default=True,
            ),
            inquirer.Confirm(
                name="dummy_load",
                message="Did you connect a dummy load? This can help to be able to measure standby power and low "
                "brightness levels correctly",
                default=False,
            ),
            inquirer.Confirm(
                name="multiple_lights",
                message="Are you measuring multiple lights. In some situations it helps to connect multiple lights to "
                "be able to measure low currents.",
                default=False,
            ),
            inquirer.Text(
                name="num_lights",
                message="How many lights are you measuring?",
                ignore=lambda answers: not answers.get("multiple_lights"),
                validate=lambda _, current: re.match(r"\d+", current),
            ),
        ]
        questions.extend(self.light_controller.get_questions())
        return questions


@dataclass(frozen=True)
class Variation:
    bri: int

    def to_csv_row(self) -> list:
        return [self.bri]


@dataclass(frozen=True)
class HsVariation(Variation):
    hue: int
    sat: int

    def to_csv_row(self) -> list:
        return [self.bri, self.hue, self.sat]

    def is_hue_changed(self, other_variation: HsVariation) -> bool:
        return self.hue != other_variation.hue

    def is_sat_changed(self, other_variation: HsVariation) -> bool:
        return self.sat != other_variation.sat


@dataclass(frozen=True)
class ColorTempVariation(Variation):
    ct: int

    def to_csv_row(self) -> list:
        return [self.bri, self.ct]

    def is_ct_changed(self, other_variation: ColorTempVariation) -> bool:
        return self.ct != other_variation.ct


class CsvWriter:
    def __init__(
        self,
        csv_file: TextIO,
        color_mode: ColorMode,
        add_header: bool,
    ) -> None:
        self.csv_file = csv_file
        self.writer = csv.writer(csv_file)
        self.rows_written = 0
        if add_header:
            header_row = CSV_HEADERS[color_mode]
            if config.CSV_ADD_DATETIME_COLUMN:
                header_row.append("time")
            self.writer.writerow(header_row)

    def write_measurement(self, variation: Variation, power: float) -> None:
        """Write row with measurement to the CSV"""
        row = variation.to_csv_row()
        row.append(power)
        if config.CSV_ADD_DATETIME_COLUMN:
            row.append(dt.now().strftime("%Y%m%d%H%M%S"))
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % CSV_WRITE_BUFFER == 1:
            self.csv_file.flush()
            _LOGGER.debug("Flushing CSV buffer")
