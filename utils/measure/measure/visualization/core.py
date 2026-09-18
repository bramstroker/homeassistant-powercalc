"""Build frontend-neutral plot specifications from measurement artifacts."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from measure.controller.light.const import LutMode
from measure.recording.files import select_recording_filenames
from measure.request import (
    ChargingMeasurementRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    SpeakerMeasurementRequest,
)
from measure.visualization.light import build_light_plot
from measure.visualization.linear import build_linear_plot
from measure.visualization.models import PlotBuildResult, PlotDataError, PlotSpec
from measure.visualization.recorder import build_recorder_plot

_LIGHT_MODE_ORDER = (LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT)


@dataclass(frozen=True)
class PlotCandidate:
    path: Path
    source: str
    max_points: int
    color_mode: LutMode | None = None


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
    for candidate in candidates:
        try:
            plots.append(
                _build_plot(
                    candidate.path,
                    source=candidate.source,
                    color_mode=candidate.color_mode,
                    max_points=candidate.max_points,
                ),
            )
        except (OSError, PlotDataError, json.JSONDecodeError) as error:
            warnings.append(f"Could not plot {candidate.source}: {error}")
    return PlotBuildResult(plots=plots, warnings=warnings)


def _session_plot_candidates(
    request: MeasurementRequest,
    files: Mapping[str, Path],
    *,
    max_scatter_points: int,
    max_line_points: int,
) -> list[PlotCandidate]:
    model_root = request.model_id or "measurement"
    if isinstance(request, LightMeasurementRequest):
        return _light_plot_candidates(request, files, model_root, max_scatter_points)
    if isinstance(request, RecorderMeasurementRequest):
        names = (Path(name).name.removesuffix(".gz") for name in files if Path(name).parent == Path(model_root))
        return [
            candidate
            for name in select_recording_filenames(names, request.export_filename)
            for candidate in _single_plot_candidate(files, f"{model_root}/{name}", max_line_points)
        ]
    if isinstance(request, SpeakerMeasurementRequest | FanMeasurementRequest | ChargingMeasurementRequest):
        return _single_plot_candidate(files, f"{model_root}/model.json", max_line_points)
    return []


def _light_plot_candidates(
    request: LightMeasurementRequest,
    files: Mapping[str, Path],
    model_root: str,
    max_points: int,
) -> list[PlotCandidate]:
    return [
        candidate
        for mode in _LIGHT_MODE_ORDER
        if mode in request.modes
        for candidate in _single_plot_candidate(files, f"{model_root}/{mode.value}.csv", max_points, mode)
    ]


def _single_plot_candidate(
    files: Mapping[str, Path],
    name: str,
    max_points: int,
    color_mode: LutMode | None = None,
) -> list[PlotCandidate]:
    for source in (name, f"{name}.gz"):
        if source in files:
            return [PlotCandidate(path=files[source], source=source, max_points=max_points, color_mode=color_mode)]
    return []


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
        return build_linear_plot(path, source=source, max_points=max_points)
    mode = color_mode or _mode_from_filename(path)
    if mode is not None:
        return build_light_plot(path, source=source, mode=mode, max_points=max_points)
    return build_recorder_plot(path, source=source, max_points=max_points)


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
