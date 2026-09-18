from collections.abc import Iterator, Sequence
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime as dt
import gzip
import io
import logging
import math
from pathlib import Path
import shutil
from typing import TextIO

from measure.controller.light.const import LutMode
from measure.runner.light.plan import ColorTempVariation, EffectVariation, HsVariation, Variation
from measure.tuning import MeasurementParameters

CSV_WRITE_BUFFER = 50
CSV_HEADERS = {
    LutMode.HS: ["bri", "hue", "sat", "watt"],
    LutMode.COLOR_TEMP: ["bri", "mired", "watt"],
    LutMode.BRIGHTNESS: ["bri", "watt"],
    LutMode.EFFECT: ["effect", "bri", "watt"],
}

_LOGGER = logging.getLogger("measure")


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
            self.writer.writerow(_build_header(mode, self.config.csv_add_datetime_column))

    def write_measurement(self, variation: Variation, power: float) -> None:
        row = variation.to_csv_row()
        row.append(power)
        if self.config.csv_add_datetime_column:
            row.append(dt.now().strftime("%Y%m%d%H%M%S"))
        self.writer.writerow(row)
        self.rows_written += 1
        if self.rows_written % CSV_WRITE_BUFFER == 1:
            self.csv_file.flush()
            _LOGGER.debug("Flushing CSV buffer")


@contextmanager
def open_csv_writer(
    path: Path, mode: LutMode, *, append: bool, parameters: MeasurementParameters
) -> Iterator[CsvWriter]:
    with path.open("a" if append else "w", encoding="utf-8", newline="") as file:
        yield CsvWriter(file, mode, add_header=not append, parameters=parameters)


def has_measurement_rows(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open(encoding="utf-8", newline="") as file:
        rows = csv.reader(file)
        next(rows, None)  # Skip the header.
        return next(rows, None) is not None


def compress_light_csv(path: Path) -> None:
    with path.open("rb") as file, gzip.open(f"{path}.gz", "wb") as compressed:
        shutil.copyfileobj(file, compressed)


def _build_header(mode: LutMode, include_datetime: bool) -> list[str]:
    header = [*CSV_HEADERS[mode]]
    if include_datetime:
        header.append("time")
    return header


def _parse_variation(row: Sequence[str], mode: LutMode) -> Variation | None:
    """Parse a variation only when its row contains a finite power reading."""
    watt_index = len(CSV_HEADERS[mode]) - 1
    try:
        if not math.isfinite(float(row[watt_index])):
            return None
        if mode == LutMode.BRIGHTNESS:
            return Variation(bri=int(row[0]))
        if mode == LutMode.COLOR_TEMP:
            return ColorTempVariation(bri=int(row[0]), ct=int(row[1]))
        if mode == LutMode.HS:
            return HsVariation(bri=int(row[0]), hue=int(row[1]), sat=int(row[2]))
        if mode == LutMode.EFFECT and row[0].strip():
            return EffectVariation(effect=row[0], bri=int(row[1]))
    except ValueError:
        return None
    return None


@dataclass
class LightCsvInspection:
    retained_rows: list[list[str]]
    last_complete_variation: Variation | None
    incomplete_tail_rows: int


def inspect_light_csv(path: Path, mode: LutMode, *, include_datetime: bool = False) -> LightCsvInspection:
    """Find the last complete measurement and any incomplete trailing rows without changing the file."""
    text = path.read_text(encoding="utf-8")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise ValueError(f"Invalid measurement CSV: {path}") from error
    if not rows:
        return LightCsvInspection([], None, 0)

    expected_header = _build_header(mode, include_datetime)
    if rows[0] != expected_header:
        raise ValueError(f"Measurement CSV header does not match the configured {mode.value} mode: {path}")

    retained_count = len(rows)
    # Even a parseable final value may be truncated if the write never reached its newline.
    if retained_count > 1 and not text.endswith(("\n", "\r")):
        retained_count -= 1
    variation = None
    while retained_count > 1:
        row = rows[retained_count - 1]
        if len(row) == len(expected_header):
            variation = _parse_variation(row, mode)
            if variation is not None:
                break
        retained_count -= 1

    return LightCsvInspection(rows[:retained_count], variation, len(rows) - retained_count)


def repair_incomplete_csv_tail(path: Path, inspection: LightCsvInspection) -> None:
    """Remove the incomplete trailing rows identified by a prior inspection."""
    if not inspection.incomplete_tail_rows:
        return
    _LOGGER.warning(
        "Dropping %d incomplete trailing row(s) from %s before resuming", inspection.incomplete_tail_rows, path
    )
    with path.open("w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(inspection.retained_rows)
