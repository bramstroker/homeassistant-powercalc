"""Build calibration plots from standalone and composite model JSON."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import TypeGuard

from measure.visualization.data import POWER_AXIS_LABEL, SERIES_COLORS, finite_float
from measure.visualization.labels import format_entity_label, format_value_label
from measure.visualization.models import PlotDataError, PlotKind, PlotPoint, PlotSeries, PlotSpec
from measure.visualization.sampling import limit_line

_COMPOSITE_STRATEGY = "composite"
_LINEAR_STRATEGY = "linear"


@dataclass(frozen=True)
class LinearCalibration:
    condition: object
    config: Mapping[str, object]


def model_has_linear_calibration(data: object) -> bool:
    """Return whether model data declares a linear calibration."""

    return bool(_linear_calibration_configs(data))


def build_linear_plot(path: Path, *, source: str, max_points: int | None) -> PlotSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    linear_configs = _linear_calibration_configs(data)
    if not linear_configs:
        raise PlotDataError("model does not contain linear calibration data")

    series_count = len(linear_configs)
    series = tuple(
        _linear_series(
            calibration.config,
            label=_condition_label(calibration.condition, index) if series_count > 1 else None,
            color=SERIES_COLORS[(index - 1) % len(SERIES_COLORS)],
            max_points=max_points,
        )
        for index, calibration in enumerate(linear_configs, start=1)
    )

    device_type = data.get("device_type") if isinstance(data, dict) else None
    title, x_label = _linear_labels(device_type if isinstance(device_type, str) else None)
    return PlotSpec(
        id="calibration",
        title=title,
        kind=PlotKind.LINE,
        x_label=x_label,
        y_label=POWER_AXIS_LABEL,
        source=source,
        series=series,
    )


def _linear_calibration_configs(data: object) -> tuple[LinearCalibration, ...]:
    if not isinstance(data, dict):
        return ()

    strategy = data.get("calculation_strategy")
    if strategy == _LINEAR_STRATEGY:
        linear_config = data.get("linear_config")
        return (LinearCalibration(condition=None, config=linear_config),) if _has_calibration(linear_config) else ()
    if strategy != _COMPOSITE_STRATEGY:
        return ()

    composite_config = data.get("composite_config")
    strategies: object
    if isinstance(composite_config, list):
        strategies = composite_config
    elif isinstance(composite_config, dict):
        strategies = composite_config.get("strategies")
    else:
        return ()
    if not isinstance(strategies, list):
        return ()

    configs: list[LinearCalibration] = []
    for strategy_config in strategies:
        if not isinstance(strategy_config, dict):
            continue
        linear_config = strategy_config.get(_LINEAR_STRATEGY)
        if _has_calibration(linear_config):
            configs.append(LinearCalibration(condition=strategy_config.get("condition"), config=linear_config))
    return tuple(configs)


def _has_calibration(config: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(config, dict) and isinstance(config.get("calibrate"), list)


def _linear_series(
    linear_config: Mapping[str, object],
    *,
    label: str | None,
    color: str,
    max_points: int | None,
) -> PlotSeries:
    calibrate = linear_config.get("calibrate")
    if not isinstance(calibrate, list):  # pragma: no cover - guarded by _linear_calibration_configs
        raise PlotDataError("model does not contain linear calibration data")

    points: list[PlotPoint] = []
    for entry in calibrate:
        if not isinstance(entry, str):
            continue
        left, separator, right = entry.partition(" -> ")
        if not separator:
            continue
        x_value = finite_float(left)
        power = finite_float(right)
        if x_value is not None and power is not None:
            points.append(PlotPoint(x=x_value, y=power))
    if not points:
        raise PlotDataError("no valid linear calibration entries found")
    points.sort(key=lambda point: point.x)
    return PlotSeries(
        label=label,
        color=color,
        points=limit_line(points, max_points),
    )


def _condition_label(condition: object, strategy_index: int) -> str:
    if not isinstance(condition, dict):
        return "Unconditional"

    condition_type = condition.get("condition")
    if condition_type in {"and", "or", "not"}:
        conditions = condition.get("conditions")
        if isinstance(conditions, list):
            labels = [_condition_label(item, strategy_index) for item in conditions]
            if labels:
                if condition_type == "not":
                    return f"NOT ({' AND '.join(labels)})"
                return f" {str(condition_type).upper()} ".join(labels)
    if condition_type == "state":
        subject = condition.get("attribute") or format_entity_label(condition.get("entity_id"))
        state = condition.get("state")
        if subject and state is not None:
            return f"{str(subject).replace('_', ' ')} = {format_value_label(state)}"
    return f"Strategy {strategy_index}"


def _linear_labels(device_type: str | None) -> tuple[str, str]:
    if device_type == "smart_speaker":
        return "Speaker calibration", "Volume (%)"
    if device_type == "fan":
        return "Fan calibration", "Fan speed (%)"
    if device_type in {"vacuum_robot", "lawn_mower_robot"}:
        return "Charging calibration", "Battery level (%)"
    return "Linear calibration", "Value"
