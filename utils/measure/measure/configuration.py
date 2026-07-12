from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MeasurementSettings:
    """Canonical measurement tuning knobs and their default values.

    This is the single source of truth for tuning defaults. Both the CLI
    (``MeasureConfig`` environment fallbacks) and the Home Assistant app
    (``AppMeasureConfig``) derive their defaults from here so the two never drift.
    """

    min_brightness: int = 1
    max_brightness: int = 255
    min_sat: int = 1
    max_sat: int = 255
    min_hue: int = 1
    max_hue: int = 65535
    brightness_step: int = 5
    color_temp_step: int = 5
    hue_step: int = 10
    saturation_step: int = 10
    effect_bri_steps: int = 40
    measure_time_effect: int = 180
    measure_time_effect_min: int = 20
    measure_time_effect_convergence_window: int = 15
    measure_time_effect_convergence_abs: float = 0.1
    measure_time_effect_convergence_rel: float = 0.01
    sleep_initial: int = 10
    sleep_standby: int = 20
    sleep_time: int = 2
    sleep_time_sample: int = 1
    sleep_time_hue: int = 5
    sleep_time_sat: int = 10
    sleep_time_ct: int = 10
    sleep_time_effect_change: int = 5
    sleep_time_nudge: float = 10
    pulse_time_nudge: float = 2
    sample_count: int = 1
    max_retries: int = 5
    max_nudges: int = 0
    light_transition_time: int = 0
    call_update_entity: bool = False
    csv_add_datetime_column: bool = False


class MeasureRuntimeConfig(Protocol):
    """Runtime tuning surface consumed by the measurement runners and ``MeasureUtil``.

    Implemented by ``MeasureConfig`` (CLI, environment-backed) and ``AppMeasureConfig``
    (Home Assistant app, derived from a measurement request).
    """

    min_brightness: int
    max_brightness: int
    min_sat: int
    max_sat: int
    min_hue: int
    max_hue: int
    ct_bri_steps: int
    ct_mired_steps: int
    bri_bri_steps: int
    hs_bri_steps: int
    hs_hue_steps: int
    hs_sat_steps: int
    effect_bri_steps: int
    measure_time_effect: int
    measure_time_effect_min: int
    measure_time_effect_convergence_window: int
    measure_time_effect_convergence_abs: float
    measure_time_effect_convergence_rel: float
    sleep_initial: int
    sleep_standby: int
    sleep_time: int
    sleep_time_sample: int
    sleep_time_hue: int
    sleep_time_sat: int
    sleep_time_ct: int
    sleep_time_effect_change: int
    sleep_time_nudge: float
    pulse_time_nudge: float
    sample_count: int
    max_retries: int
    max_nudges: int
    resume: bool
    prompt_resume: bool
    csv_add_datetime_column: bool
