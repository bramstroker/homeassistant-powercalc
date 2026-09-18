"""Frontend-neutral plot specifications."""

from dataclasses import dataclass
from enum import StrEnum


class PlotKind(StrEnum):
    SCATTER = "scatter"
    LINE = "line"


@dataclass(frozen=True, slots=True)
class PlotPoint:
    x: float
    y: float
    color: str | None = None


@dataclass(frozen=True, slots=True)
class PlotSeries:
    label: str | None
    color: str | None
    points: list[PlotPoint]


@dataclass(frozen=True, slots=True)
class PlotSpec:
    id: str
    title: str
    kind: PlotKind
    x_label: str
    y_label: str
    source: str
    series: list[PlotSeries]


@dataclass(frozen=True, slots=True)
class PlotBuildResult:
    plots: list[PlotSpec]
    warnings: list[str]


class PlotDataError(ValueError):
    """Raised when an artifact cannot produce a valid plot."""
