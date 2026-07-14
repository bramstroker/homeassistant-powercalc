from enum import StrEnum
import os
from pathlib import Path

QUESTION_GENERATE_MODEL_JSON = "generate_model_json"
QUESTION_DUMMY_LOAD = "dummy_load"
QUESTION_MODEL_NAME = "model_name"
QUESTION_MEASURE_DEVICE = "measure_device"
QUESTION_ENTITY_ID = "entity_id"
QUESTION_MODEL_ID = "model_id"
QUESTION_SELECTED_MEASURE_TYPE = "selected_measure_type"
MODEL_JSON_MAX_VOLTAGE = "max_voltage"
MODEL_JSON_MIN_VOLTAGE = "min_voltage"
HASS_DEVICE_REGISTRY_LIST = "config/device_registry/list"
HASS_DEVICE_REGISTRY_ID = "id"
HASS_DEVICE_REGISTRY_MODEL = "model"
HASS_DEVICE_REGISTRY_MODEL_ID = "model_id"

script_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = Path(os.path.join(script_dir, "../")).resolve()


class MeasureType(StrEnum):
    """Stable machine identifiers for supported measurement workflows."""

    LIGHT = "light"
    SPEAKER = "speaker"
    RECORDER = "recorder"
    AVERAGE = "average"
    CHARGING = "charging"
    FAN = "fan"


MEASURE_TYPE_LABELS: dict[MeasureType, str] = {
    MeasureType.LIGHT: "Light bulb(s)",
    MeasureType.SPEAKER: "Smart speaker",
    MeasureType.RECORDER: "Recorder",
    MeasureType.AVERAGE: "Average",
    MeasureType.CHARGING: "Charging device",
    MeasureType.FAN: "Fan",
}

LEGACY_MEASURE_TYPE_VALUES: dict[str, MeasureType] = {
    label: measure_type for measure_type, label in MEASURE_TYPE_LABELS.items()
}


def parse_measure_type(value: str | MeasureType) -> MeasureType:
    """Parse current stable IDs and pre-0.1 display-label identifiers."""
    if isinstance(value, MeasureType):
        return value
    legacy = LEGACY_MEASURE_TYPE_VALUES.get(value)
    return legacy if legacy is not None else MeasureType(value)


class Trend(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STEADY = "steady"


DUMMY_LOAD_MEASUREMENT_COUNT = 20
DUMMY_LOAD_MEASUREMENTS_DURATION = 30
RETRY_COUNT_LIMIT = 100

MEASUREMENT_SLEEP_TIME_MIN = 0
MEASUREMENT_SLEEP_TIME_MAX = 120
MEASUREMENT_SAMPLE_COUNT_MIN = 1
MEASUREMENT_SAMPLE_COUNT_MAX = 100
MAX_NUDGES_LIMIT = 20

# Single source of measurement-parameter bounds. Request validation, persisted app
# preferences and the capabilities endpoint (which the frontend forms read) all
# derive from this table so the layers cannot drift apart.
PARAMETER_LIMITS: dict[str, tuple[float, float]] = {
    "sleep_time": (MEASUREMENT_SLEEP_TIME_MIN, MEASUREMENT_SLEEP_TIME_MAX),
    "sample_count": (MEASUREMENT_SAMPLE_COUNT_MIN, MEASUREMENT_SAMPLE_COUNT_MAX),
    "sleep_time_sample": (0, MEASUREMENT_SLEEP_TIME_MAX),
    "max_retries": (0, RETRY_COUNT_LIMIT),
    "max_nudges": (0, MAX_NUDGES_LIMIT),
    "min_brightness": (1, 255),
    "brightness_step": (1, 100),
    "hue_step": (1, 360),
    "saturation_step": (1, 100),
    "color_temp_step": (1, 100),
    "effect_bri_steps": (1, 255),
    "sleep_initial": (0, 3600),
    "sleep_standby": (0, 3600),
    "measure_time_effect": (1, 3600),
    "measure_time_effect_min": (1, 3600),
}
