from __future__ import annotations

from typing import Protocol


class MeasureRuntimeConfig(Protocol):
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
