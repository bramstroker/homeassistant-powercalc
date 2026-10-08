"""Shared plot styling and artifact value readers."""

import gzip
import math
from pathlib import Path
from typing import TextIO

DEFAULT_COLOR = "#5488e8"
SERIES_COLORS = (
    "#5488e8",
    "#61d4a3",
    "#f0b45b",
    "#d27df2",
    "#ff7b72",
    "#68c9e8",
    "#b8d45f",
    "#f28bb7",
)

POWER_AXIS_LABEL = "Power (W)"


def open_csv(path: Path) -> TextIO:
    # utf-8-sig strips a leading BOM if present (some measurement CSVs carry one) and is otherwise identical to utf-8.
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None
