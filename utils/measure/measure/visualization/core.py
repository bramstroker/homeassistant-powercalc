"""Build frontend-neutral plot specifications from measurement artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import colorsys
import csv
from dataclasses import dataclass
from enum import StrEnum
import gzip
import json
import math
from pathlib import Path
from typing import TextIO

from measure.controller.light.const import LutMode
from measure.request import (
    ChargingMeasurementRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    SpeakerMeasurementRequest,
)

_DEFAULT_COLOR = "#5488e8"
_EFFECT_COLORS = (
    "#5488e8",
    "#61d4a3",
    "#f0b45b",
    "#d27df2",
    "#ff7b72",
    "#68c9e8",
    "#b8d45f",
    "#f28bb7",
)
_LIGHT_MODE_ORDER = (LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT)
_POWER_AXIS_LABEL = "Power (W)"


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
    points: tuple[PlotPoint, ...]


@dataclass(frozen=True, slots=True)
class PlotSpec:
    id: str
    title: str
    kind: PlotKind
    x_label: str
    y_label: str
    source: str
    series: tuple[PlotSeries, ...]


@dataclass(frozen=True, slots=True)
class PlotBuildResult:
    plots: tuple[PlotSpec, ...]
    warnings: tuple[str, ...]


class PlotDataError(ValueError):
    """Raised when an artifact cannot produce a valid plot."""


def build_session_plots(
    request: MeasurementRequest,
    files: Mapping[str, Path],
    *,
    max_scatter_points: int = 10_000,
    max_line_points: int = 4_000,
) -> PlotBuildResult:
    """Build every meaningful plot available for a persisted measurement."""

    candidates = _session_plot_candidates(
        request,
        files,
        max_scatter_points=max_scatter_points,
        max_line_points=max_line_points,
    )
    plots: list[PlotSpec] = []
    warnings: list[str] = []
    for path, source, mode, max_points in candidates:
        try:
            plots.append(
                _build_plot(
                    path,
                    source=source,
                    color_mode=mode,
                    max_points=max_points,
                ),
            )
        except (OSError, PlotDataError, json.JSONDecodeError) as error:
            warnings.append(f"Could not plot {source}: {error}")
    return PlotBuildResult(plots=tuple(plots), warnings=tuple(warnings))


def _session_plot_candidates(
    request: MeasurementRequest,
    files: Mapping[str, Path],
    *,
    max_scatter_points: int,
    max_line_points: int,
) -> list[tuple[Path, str, LutMode | None, int]]:
    candidates: list[tuple[Path, str, LutMode | None, int]] = []
    model_root = request.model_id
    if isinstance(request, LightMeasurementRequest):
        for mode in _LIGHT_MODE_ORDER:
            if mode not in request.modes:
                continue
            candidate = _preferred_file(files, f"{model_root}/{mode.value}.csv")
            if candidate is not None:
                candidates.append((*candidate, mode, max_scatter_points))
    elif isinstance(request, RecorderMeasurementRequest):
        candidate = _preferred_file(files, f"{model_root}/{request.export_filename}")
        if candidate is not None:
            candidates.append((*candidate, None, max_line_points))
    elif isinstance(request, SpeakerMeasurementRequest | FanMeasurementRequest | ChargingMeasurementRequest):
        candidate = _preferred_file(files, f"{model_root}/model.json")
        if candidate is not None:
            candidates.append((*candidate, None, max_line_points))
    return candidates


def build_plot_from_file(
    path: str | Path,
    *,
    color_mode: str | LutMode | None = None,
    max_points: int | None = None,
) -> PlotSpec:
    """Build one plot from a standalone CSV, CSV.GZ or model.json artifact."""

    file_path = Path(path)
    resolved_mode = _parse_mode(color_mode) if color_mode is not None else None
    return _build_plot(
        file_path,
        source=file_path.name,
        color_mode=resolved_mode,
        max_points=max_points,
    )


def _build_plot(
    path: Path,
    *,
    source: str,
    color_mode: LutMode | None,
    max_points: int | None,
) -> PlotSpec:
    if path.name.endswith(".json"):
        return _linear_plot(path, source=source, max_points=max_points)
    mode = color_mode or _mode_from_filename(path)
    if mode is not None:
        return _light_plot(path, source=source, mode=mode, max_points=max_points)
    return _recorder_plot(path, source=source, max_points=max_points)


def _light_plot(path: Path, *, source: str, mode: LutMode, max_points: int | None) -> PlotSpec:
    expected_fields = {
        LutMode.BRIGHTNESS: {"bri", "watt"},
        LutMode.COLOR_TEMP: {"bri", "mired", "watt"},
        LutMode.HS: {"bri", "hue", "sat", "watt"},
        LutMode.EFFECT: {"effect", "bri", "watt"},
    }[mode]
    with _open_csv(path) as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not expected_fields.issubset(reader.fieldnames):
            raise PlotDataError(f"expected CSV columns: {', '.join(sorted(expected_fields))}")
        rows = list(reader)

    if mode is LutMode.EFFECT:
        series = _effect_series(rows, max_points)
    else:
        series = _single_light_series(rows, mode, max_points)

    title = {
        LutMode.BRIGHTNESS: "Brightness",
        LutMode.COLOR_TEMP: "Color temperature",
        LutMode.HS: "Hue and saturation",
        LutMode.EFFECT: "Effects",
    }[mode]
    return PlotSpec(
        id=mode.value,
        title=title,
        kind=PlotKind.SCATTER,
        x_label="Brightness",
        y_label=_POWER_AXIS_LABEL,
        source=source,
        series=series,
    )


def _effect_series(rows: list[dict[str, str | None]], max_points: int | None) -> tuple[PlotSeries, ...]:
    grouped: dict[str, list[PlotPoint]] = {}
    for row in rows:
        effect = str(row.get("effect", "")).strip()
        point = _light_point(row, LutMode.EFFECT)
        if effect and point is not None:
            grouped.setdefault(effect, []).append(point)
    if not grouped:
        raise PlotDataError("no valid effect measurements found")
    return tuple(
        PlotSeries(
            label=effect,
            color=_EFFECT_COLORS[index % len(_EFFECT_COLORS)],
            points=_limit_scatter(points, max_points),
        )
        for index, (effect, points) in enumerate(grouped.items())
    )


def _single_light_series(
    rows: list[dict[str, str | None]],
    mode: LutMode,
    max_points: int | None,
) -> tuple[PlotSeries, ...]:
    points = [point for row in rows if (point := _light_point(row, mode)) is not None]
    if not points:
        raise PlotDataError("no valid light measurements found")
    return (
        PlotSeries(
            label=None,
            color=_DEFAULT_COLOR if mode is LutMode.BRIGHTNESS else None,
            points=_limit_scatter(points, max_points),
        ),
    )


def _light_point(row: Mapping[str, str | None], mode: LutMode) -> PlotPoint | None:
    brightness = _finite_float(row.get("bri"))
    power = _finite_float(row.get("watt"))
    if brightness is None or power is None:
        return None
    color = None
    if mode is LutMode.COLOR_TEMP:
        mired = _finite_float(row.get("mired"))
        if mired is None or mired <= 0:
            return None
        color = _mired_color(mired)
    elif mode is LutMode.HS:
        hue = _finite_float(row.get("hue"))
        saturation = _finite_float(row.get("sat"))
        if hue is None or saturation is None:
            return None
        red, green, blue = colorsys.hls_to_rgb(hue / 65535, brightness / 255, saturation / 255)
        color = _rgb_color(red * 255, green * 255, blue * 255)
    return PlotPoint(x=brightness, y=power, color=color)


def _linear_plot(path: Path, *, source: str, max_points: int | None) -> PlotSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("calculation_strategy") != "linear":
        raise PlotDataError("model does not contain a linear calculation strategy")
    linear_config = data.get("linear_config")
    calibrate = linear_config.get("calibrate") if isinstance(linear_config, dict) else None
    if not isinstance(calibrate, list):
        raise PlotDataError("model does not contain linear calibration data")

    points: list[PlotPoint] = []
    for entry in calibrate:
        if not isinstance(entry, str):
            continue
        left, separator, right = entry.partition(" -> ")
        if not separator:
            continue
        x_value = _finite_float(left)
        power = _finite_float(right)
        if x_value is not None and power is not None:
            points.append(PlotPoint(x=x_value, y=power))
    if not points:
        raise PlotDataError("no valid linear calibration entries found")
    points.sort(key=lambda point: point.x)

    device_type = data.get("device_type")
    title, x_label = _linear_labels(device_type if isinstance(device_type, str) else None)
    return PlotSpec(
        id="calibration",
        title=title,
        kind=PlotKind.LINE,
        x_label=x_label,
        y_label=_POWER_AXIS_LABEL,
        source=source,
        series=(
            PlotSeries(
                label=None,
                color=_DEFAULT_COLOR,
                points=_limit_line(points, max_points),
            ),
        ),
    )


def _recorder_plot(path: Path, *, source: str, max_points: int | None) -> PlotSpec:
    points: list[PlotPoint] = []
    with _open_csv(path) as file:
        for row in csv.reader(file):
            if len(row) < 2:
                continue
            elapsed = _finite_float(row[0])
            power = _finite_float(row[1])
            if elapsed is not None and power is not None:
                points.append(PlotPoint(x=elapsed, y=power))
    if not points:
        raise PlotDataError("no valid recorder measurements found")
    return PlotSpec(
        id="recording",
        title="Power recording",
        kind=PlotKind.LINE,
        x_label="Elapsed time (s)",
        y_label=_POWER_AXIS_LABEL,
        source=source,
        series=(
            PlotSeries(
                label=None,
                color=_DEFAULT_COLOR,
                points=_limit_line(points, max_points),
            ),
        ),
    )


def _preferred_file(files: Mapping[str, Path], name: str) -> tuple[Path, str] | None:
    if name in files:
        return files[name], name
    compressed_name = f"{name}.gz"
    if compressed_name in files:
        return files[compressed_name], compressed_name
    return None


def _parse_mode(value: str | LutMode) -> LutMode:
    if isinstance(value, LutMode):
        return value
    normalized = value.removesuffix("s") if value == "effects" else value
    try:
        return LutMode(normalized)
    except ValueError as error:
        raise PlotDataError(f"unsupported light mode: {value}") from error


def _mode_from_filename(path: Path) -> LutMode | None:
    name = path.name.removesuffix(".gz").removesuffix(".csv")
    if name == "effects":
        name = "effect"
    try:
        return LutMode(name)
    except ValueError:
        return None


def _linear_labels(device_type: str | None) -> tuple[str, str]:
    if device_type == "smart_speaker":
        return "Speaker calibration", "Volume (%)"
    if device_type == "fan":
        return "Fan calibration", "Fan speed (%)"
    if device_type in {"vacuum_robot", "lawn_mower_robot"}:
        return "Charging calibration", "Battery level (%)"
    return "Linear calibration", "Value"


def _limit_scatter(points: Sequence[PlotPoint], max_points: int | None) -> tuple[PlotPoint, ...]:
    if max_points is None or len(points) <= max_points:
        return tuple(points)
    if max_points <= 1:
        return (points[0],)
    return tuple(points[round(index * (len(points) - 1) / (max_points - 1))] for index in range(max_points))


def _limit_line(points: Sequence[PlotPoint], max_points: int | None) -> tuple[PlotPoint, ...]:
    if max_points is None or len(points) <= max_points:
        return tuple(points)
    if max_points < 4:
        return _limit_scatter(points, max_points)

    indexed = list(enumerate(points))
    interior = indexed[1:-1]
    bucket_count = max(1, (max_points - 2) // 2)
    bucket_size = math.ceil(len(interior) / bucket_count)
    selected: list[tuple[int, PlotPoint]] = [indexed[0]]
    for start in range(0, len(interior), bucket_size):
        bucket = interior[start : start + bucket_size]
        minimum = min(bucket, key=lambda item: item[1].y)
        maximum = max(bucket, key=lambda item: item[1].y)
        selected.extend(sorted({minimum[0]: minimum, maximum[0]: maximum}.values()))
    selected.append(indexed[-1])
    return tuple(point for _, point in sorted(selected)[:max_points])


def _open_csv(path: Path) -> TextIO:
    # utf-8-sig strips a leading BOM if present (some measurement CSVs carry one) and is otherwise identical to utf-8.
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _mired_color(mired: float) -> str:
    temperature = min(40_000.0, max(1_000.0, 1_000_000.0 / mired)) / 100.0
    if temperature <= 66:
        red = 255.0
        green = 99.4708025861 * math.log(temperature) - 161.1195681661
    else:
        red = 329.698727446 * math.pow(temperature - 60, -0.1332047592)
        green = 288.1221695283 * math.pow(temperature - 60, -0.0755148492)
    if temperature >= 66:
        blue = 255.0
    elif temperature <= 19:
        blue = 0.0
    else:
        blue = 138.5177312231 * math.log(temperature - 10) - 305.0447927307
    return _rgb_color(red, green, blue)


def _rgb_color(red: float, green: float, blue: float) -> str:
    channels: Iterable[int] = (round(min(255.0, max(0.0, channel))) for channel in (red, green, blue))
    return "#" + "".join(f"{channel:02x}" for channel in channels)
