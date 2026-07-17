from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from measure.const import MODEL_JSON_MAX_VOLTAGE, MODEL_JSON_MIN_VOLTAGE
from measure.tuning import MeasurementParameters
from measure.version import measure_version


def write_model_json(
    directory: Path,
    *,
    standby_power: float,
    name: str,
    measure_device: str,
    parameters: MeasurementParameters,
    extra_json_data: dict[str, Any] | None = None,
    voltages: list[float] | None = None,
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
    if voltages:
        json_data.update(
            {
                MODEL_JSON_MIN_VOLTAGE: round(min(voltages), 2),
                MODEL_JSON_MAX_VOLTAGE: round(max(voltages), 2),
            },
        )
    if extra_json_data:
        json_data.update(extra_json_data)

    path = directory / "model.json"
    path.write_text(json.dumps(json_data, indent=2, sort_keys=True), encoding="utf-8")
    return path
