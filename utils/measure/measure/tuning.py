from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MeasurementParameters:
    """Canonical timing and native light-grid parameters."""

    min_brightness: int = 1
    max_brightness: int = 255
    min_sat: int = 1
    max_sat: int = 255
    min_hue: int = 1
    max_hue: int = 65535
    bri_bri_steps: int = 1
    ct_bri_steps: int = 5
    ct_mired_steps: int = 10
    hs_bri_steps: int = 32
    hs_hue_steps: int = 2731
    hs_sat_steps: int = 32
    effect_bri_steps: int = 40
    measure_time_effect: int = 180
    measure_time_effect_min: int = 20
    measure_time_effect_convergence_window: int = 15
    measure_time_effect_convergence_abs: float = 0.1
    measure_time_effect_convergence_rel: float = 0.01
    sleep_initial: int = 10
    sleep_standby: int = 20
    sleep_time: float = 2
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
    prompt_resume: bool = False
    csv_add_datetime_column: bool = False
