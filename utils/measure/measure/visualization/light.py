"""Build light scatter plots from LUT CSV files."""

from collections.abc import Iterable, Mapping
import colorsys
import csv
import math
from pathlib import Path

from measure.controller.light.const import LutMode
from measure.visualization.data import DEFAULT_COLOR, POWER_AXIS_LABEL, SERIES_COLORS, finite_float, open_csv
from measure.visualization.models import PlotDataError, PlotKind, PlotPoint, PlotSeries, PlotSpec
from measure.visualization.sampling import limit_scatter


def build_light_plot(path: Path, *, source: str, mode: LutMode, max_points: int | None) -> PlotSpec:
    expected_fields = {
        LutMode.BRIGHTNESS: {"bri", "watt"},
        LutMode.COLOR_TEMP: {"bri", "mired", "watt"},
        LutMode.HS: {"bri", "hue", "sat", "watt"},
        LutMode.EFFECT: {"effect", "bri", "watt"},
    }[mode]
    with open_csv(path) as file:
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
        y_label=POWER_AXIS_LABEL,
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
            color=SERIES_COLORS[index % len(SERIES_COLORS)],
            points=limit_scatter(points, max_points),
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
            color=DEFAULT_COLOR if mode is LutMode.BRIGHTNESS else None,
            points=limit_scatter(points, max_points),
        ),
    )


def _light_point(row: Mapping[str, str | None], mode: LutMode) -> PlotPoint | None:
    brightness = finite_float(row.get("bri"))
    power = finite_float(row.get("watt"))
    if brightness is None or power is None:
        return None
    color = None
    if mode is LutMode.COLOR_TEMP:
        mired = finite_float(row.get("mired"))
        if mired is None or mired <= 0:
            return None
        color = _mired_color(mired)
    elif mode is LutMode.HS:
        hue = finite_float(row.get("hue"))
        saturation = finite_float(row.get("sat"))
        if hue is None or saturation is None:
            return None
        red, green, blue = colorsys.hls_to_rgb(hue / 65535, brightness / 255, saturation / 255)
        color = _rgb_color(red * 255, green * 255, blue * 255)
    return PlotPoint(x=brightness, y=power, color=color)


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
