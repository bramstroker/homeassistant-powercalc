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
HASS_ENTITY_REGISTRY_LIST = "config/entity_registry/list"
HASS_ZEROCONF_SUBSCRIBE_DISCOVERY = "zeroconf/subscribe_discovery"
HASS_DEVICE_REGISTRY_ID = "id"
HASS_DEVICE_REGISTRY_MODEL = "model"
HASS_DEVICE_REGISTRY_MODEL_ID = "model_id"
HASS_ENTITY_REGISTRY_UNIQUE_ID = "unique_id"
HASS_ENTITY_DEVICE_CLASS = "device_class"
HASS_ENTITY_UNIT_OF_MEASUREMENT = "unit_of_measurement"
ZEROCONF_HTTP_SERVICE_TYPE = "_http._tcp.local."
ZEROCONF_SHELLY_SERVICE_TYPE = "_shelly._tcp.local."
SHELLY_DISCOVERY_COLLECTION_WINDOW_SECONDS = 2.0
SHELLY_DISCOVERY_PROBE_TIMEOUT_SECONDS = 2
SHELLY_DISCOVERY_MAX_CONCURRENT_PROBES = 8

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
    UNSTABLE = "unstable"


DUMMY_LOAD_MEASUREMENT_COUNT = 20
DUMMY_LOAD_MEASUREMENTS_DURATION = 30
# Fraction of the mean resistance a per-sample slope must exceed to count as drift.
# Relative, so meter noise on high-ohm loads (a few Ω on multiple kΩ) stays below it
# while genuine warm-up drift (~0.5% per half-run) is still detected.
DUMMY_LOAD_TREND_RELATIVE_THRESHOLD = 0.0005
RETRY_COUNT_LIMIT = 100

MEASUREMENT_SLEEP_TIME_MIN = 0
MEASUREMENT_SLEEP_TIME_MAX = 120
MEASUREMENT_SAMPLE_COUNT_MIN = 1
MEASUREMENT_SAMPLE_COUNT_MAX = 100
MAX_NUDGES_LIMIT = 20
# Density guard: automated sessions may not produce ct profiles coarser than step 10.
CT_STEPS_MAX = 10

# Single source of measurement-parameter bounds. Request validation, persisted app
# preferences, the capabilities endpoint (which the frontend forms read) and the
# CLI environment layer all derive from this table so the layers cannot drift apart.
PARAMETER_LIMITS: dict[str, tuple[float, float]] = {
    "sleep_time": (MEASUREMENT_SLEEP_TIME_MIN, MEASUREMENT_SLEEP_TIME_MAX),
    "sample_count": (MEASUREMENT_SAMPLE_COUNT_MIN, MEASUREMENT_SAMPLE_COUNT_MAX),
    "sleep_time_sample": (0, MEASUREMENT_SLEEP_TIME_MAX),
    "max_retries": (0, RETRY_COUNT_LIMIT),
    "max_nudges": (0, MAX_NUDGES_LIMIT),
    "min_brightness": (1, 255),
    "min_sat": (1, 255),
    "max_sat": (1, 255),
    "min_hue": (1, 65535),
    "max_hue": (1, 65535),
    "bri_bri_steps": (1, 255),
    "ct_bri_steps": (1, CT_STEPS_MAX),
    "ct_mired_steps": (1, CT_STEPS_MAX),
    "hs_bri_steps": (1, 255),
    "hs_hue_steps": (1, 65535),
    "hs_sat_steps": (1, 255),
    "effect_bri_steps": (1, 255),
    "sleep_initial": (0, 3600),
    "sleep_standby": (0, 3600),
    "measure_time_effect": (1, 3600),
    "measure_time_effect_min": (1, 3600),
}

CT_BRI_STEPS_MANUAL = 15
CT_MIRED_STEPS_MANUAL = 50
# Manual meters get a coarser fixed ct grid than the density guard allows,
# because hand-reading every step is laborious.
MANUAL_PARAMETER_LIMIT_OVERRIDES: dict[str, tuple[float, float]] = {
    "ct_bri_steps": (1, CT_BRI_STEPS_MANUAL),
    "ct_mired_steps": (1, CT_MIRED_STEPS_MANUAL),
}
