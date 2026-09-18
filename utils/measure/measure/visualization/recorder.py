"""Stream power recordings into time-series plots with bounded point counts."""

from collections.abc import Iterable
import csv
import json
import math
from pathlib import Path

from measure.visualization.data import DEFAULT_COLOR, POWER_AXIS_LABEL, finite_float, open_csv
from measure.visualization.models import PlotDataError, PlotKind, PlotPoint, PlotSeries, PlotSpec


def build_recorder_plot(path: Path, *, source: str, max_points: int | None) -> PlotSpec:
    points = _stream_recorder_points(path, max_points)
    if not points:
        raise PlotDataError("no valid recorder measurements found")
    return PlotSpec(
        id=f"recording:{source}",
        title="Power recording",
        kind=PlotKind.LINE,
        x_label="Elapsed time (s)",
        y_label=POWER_AXIS_LABEL,
        source=source,
        series=[PlotSeries(label=None, color=DEFAULT_COLOR, points=points)],
    )


def _iter_recorder_points(path: Path) -> Iterable[PlotPoint]:
    if path.name.lower().endswith(".jsonl"):
        yield from _iter_jsonl_recorder_points(path)
        return
    with open_csv(path) as file:
        for row in csv.reader(file):
            if len(row) < 2:
                continue
            elapsed = finite_float(row[0])
            power = finite_float(row[1])
            if elapsed is not None and power is not None:
                yield PlotPoint(x=elapsed, y=power)


def _iter_jsonl_recorder_points(path: Path) -> Iterable[PlotPoint]:
    with path.open(encoding="utf-8-sig") as file:
        for line in file:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            elapsed = finite_float(row.get("elapsed_seconds"))
            power = finite_float(row.get("power"))
            if elapsed is not None and power is not None:
                yield PlotPoint(x=elapsed, y=power)


def _stream_recorder_points(path: Path, max_points: int | None) -> list[PlotPoint]:
    if max_points is None:
        return list(_iter_recorder_points(path))

    point_count = sum(1 for _ in _iter_recorder_points(path))
    if point_count <= max_points:
        return list(_iter_recorder_points(path))
    return _downsample_recorder_points(path, point_count, max_points)


def _downsample_recorder_points(path: Path, point_count: int, max_points: int) -> list[PlotPoint]:
    if max_points <= 1:
        return [point for index, point in enumerate(_iter_recorder_points(path)) if index == 0]
    if max_points < 4:
        selected_indexes = {round(index * (point_count - 1) / (max_points - 1)) for index in range(max_points)}
        return [point for index, point in enumerate(_iter_recorder_points(path)) if index in selected_indexes]
    return _recorder_extrema(path, point_count, max_points)


def _recorder_extrema(path: Path, point_count: int, max_points: int) -> list[PlotPoint]:
    bucket_count = max(1, (max_points - 2) // 2)
    bucket_size = math.ceil((point_count - 2) / bucket_count)
    selected: list[tuple[int, PlotPoint]] = []
    bucket_minimum: tuple[int, PlotPoint] | None = None
    bucket_maximum: tuple[int, PlotPoint] | None = None
    current_bucket = -1
    last: tuple[int, PlotPoint] | None = None
    for index, point in enumerate(_iter_recorder_points(path)):
        if index == 0:
            selected.append((index, point))
            continue
        if index == point_count - 1:
            last = (index, point)
            continue
        bucket_index = (index - 1) // bucket_size
        if bucket_index != current_bucket:
            _append_bucket_extrema(selected, bucket_minimum, bucket_maximum)
            bucket_minimum = None
            bucket_maximum = None
            current_bucket = bucket_index
        candidate = (index, point)
        if bucket_minimum is None or point.y < bucket_minimum[1].y:
            bucket_minimum = candidate
        if bucket_maximum is None or point.y > bucket_maximum[1].y:
            bucket_maximum = candidate
    _append_bucket_extrema(selected, bucket_minimum, bucket_maximum)
    if last is not None:
        selected.append(last)
    return [point for _, point in selected[:max_points]]


def _append_bucket_extrema(
    selected: list[tuple[int, PlotPoint]],
    minimum: tuple[int, PlotPoint] | None,
    maximum: tuple[int, PlotPoint] | None,
) -> None:
    if minimum is None or maximum is None:
        return
    selected.extend(sorted({minimum[0]: minimum, maximum[0]: maximum}.values()))
