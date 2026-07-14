from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MeasurementParameters:
    """Canonical measurement parameters with derived runner-native steps."""

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
    ct_bri_steps: int | None = None
    ct_mired_steps: int | None = None
    bri_bri_steps: int | None = None
    hs_bri_steps: int | None = None
    hs_hue_steps: int | None = None
    hs_sat_steps: int | None = None
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

    @property
    def resolved_ct_bri_steps(self) -> int:
        return (
            self.ct_bri_steps
            if self.ct_bri_steps is not None
            else self._percentage_to_native(self.brightness_step, 255)
        )

    def resolve_ct_mired_steps(self, min_mired: int, max_mired: int) -> int:
        if self.ct_mired_steps is not None:
            return self.ct_mired_steps
        return self._percentage_to_native(self.color_temp_step, max_mired - min_mired)

    @property
    def resolved_bri_bri_steps(self) -> int:
        return (
            self.bri_bri_steps
            if self.bri_bri_steps is not None
            else self._percentage_to_native(self.brightness_step, 255)
        )

    @property
    def resolved_hs_bri_steps(self) -> int:
        if self.hs_bri_steps is not None:
            return self.hs_bri_steps
        return self._percentage_to_native(self.brightness_step, 255)

    @property
    def resolved_hs_hue_steps(self) -> int:
        if self.hs_hue_steps is not None:
            return self.hs_hue_steps
        return self._percentage_to_native(self.hue_step, 65535, scale=360)

    @property
    def resolved_hs_sat_steps(self) -> int:
        if self.hs_sat_steps is not None:
            return self.hs_sat_steps
        return self._percentage_to_native(self.saturation_step, 255)

    @staticmethod
    def _percentage_to_native(value: int, native_range: int, *, scale: int = 100) -> int:
        return max(1, round(value / scale * native_range))
