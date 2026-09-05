from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Literal

from measure.const import (
    MODEL_JSON_VOLTAGE_RANGE,
    MODEL_JSON_VOLTAGE_RANGE_MAX,
    MODEL_JSON_VOLTAGE_RANGE_MIN,
)
from measure.tuning import MeasurementParameters
from measure.version import measure_version


def mains_voltage_from_range(voltage_range: object) -> Literal[120, 230] | None:
    """Return the nominal mains voltage represented by an observed range."""
    if not isinstance(voltage_range, dict):
        return None
    minimum = voltage_range.get(MODEL_JSON_VOLTAGE_RANGE_MIN)
    maximum = voltage_range.get(MODEL_JSON_VOLTAGE_RANGE_MAX)
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int | float)
        or not isinstance(maximum, int | float)
        or minimum > maximum
    ):
        return None
    midpoint = (minimum + maximum) / 2
    return 120 if abs(120 - midpoint) <= abs(230 - midpoint) else 230


def write_model_json(
    directory: Path,
    *,
    standby_power: float,
    name: str,
    measure_device: str,
    parameters: MeasurementParameters,
    extra_json_data: dict[str, Any] | None = None,
    voltages: list[float] | None = None,
    num_lights: int | None = None,
) -> Path:
    created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    json_data: dict[str, Any] = {
        "created_at": created_at,
        "measure_device": measure_device,
        "measure_method": "script",
        "measure_description": "Measured with utils/measure script",
        "measure_settings": {
            "VERSION": measure_version(),
            "SAMPLE_COUNT": parameters.sample_count,
            "SLEEP_TIME": parameters.sleep_time,
        },
        "name": name,
        "standby_power": standby_power,
    }
    if num_lights is not None:
        json_data["measure_settings"]["NUM_LIGHTS"] = num_lights
    if voltages:
        voltage_range = {
            MODEL_JSON_VOLTAGE_RANGE_MIN: round(min(voltages), 2),
            MODEL_JSON_VOLTAGE_RANGE_MAX: round(max(voltages), 2),
        }
        json_data[MODEL_JSON_VOLTAGE_RANGE] = voltage_range
        json_data["mains_voltage"] = mains_voltage_from_range(voltage_range)
    if extra_json_data:
        json_data.update(extra_json_data)

    path = directory / "model.json"
    path.write_text(json.dumps(json_data, indent=2, sort_keys=True), encoding="utf-8")
    return path
