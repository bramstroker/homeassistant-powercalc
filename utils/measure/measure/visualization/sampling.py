"""Downsample plot series, preserving line endpoints and bucket extrema."""

from collections.abc import Sequence
from dataclasses import replace
import math

from measure.visualization.models import PlotKind, PlotPoint, PlotSpec


def limit_plot_points(plot: PlotSpec, max_points: int) -> PlotSpec:
    """Return the plot with every series downsampled to at most max_points."""

    limit = limit_line if plot.kind is PlotKind.LINE else limit_scatter
    limited: PlotSpec = replace(
        plot,
        series=[replace(series, points=limit(series.points, max_points)) for series in plot.series],
    )
    return limited


def limit_scatter(points: Sequence[PlotPoint], max_points: int | None) -> list[PlotPoint]:
    if max_points is None or len(points) <= max_points:
        return list(points)
    if max_points <= 1:
        return [points[0]]
    return [points[round(index * (len(points) - 1) / (max_points - 1))] for index in range(max_points)]


def limit_line(points: Sequence[PlotPoint], max_points: int | None) -> list[PlotPoint]:
    if max_points is None or len(points) <= max_points:
        return list(points)
    if max_points < 4:
        return limit_scatter(points, max_points)

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
    return [point for _, point in sorted(selected)[:max_points]]
