from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
import math

from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightInfo
from measure.runner.errors import RunnerError
from measure.tuning import MeasurementParameters

ESTIMATED_IO_DELAY = 0.15
LIGHT_MODE_ORDER = (LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT)

CSV_HEADERS = {
    LutMode.HS: ["bri", "hue", "sat", "watt"],
    LutMode.COLOR_TEMP: ["bri", "mired", "watt"],
    LutMode.BRIGHTNESS: ["bri", "watt"],
    LutMode.EFFECT: ["effect", "bri", "watt"],
}


@dataclass(frozen=True)
class Variation:
    bri: int

    def to_csv_row(self) -> list[str | int | float]:
        return [self.bri]

    @property
    def mode(self) -> LutMode:
        return LutMode.BRIGHTNESS


@dataclass(frozen=True)
class HsVariation(Variation):
    hue: int
    sat: int

    def to_csv_row(self) -> list[str | int | float]:
        return [self.bri, self.hue, self.sat]

    @property
    def mode(self) -> LutMode:
        return LutMode.HS


@dataclass(frozen=True)
class ColorTempVariation(Variation):
    ct: int

    def to_csv_row(self) -> list[str | int | float]:
        return [self.bri, self.ct]

    @property
    def mode(self) -> LutMode:
        return LutMode.COLOR_TEMP


@dataclass(frozen=True)
class EffectVariation(Variation):
    effect: str

    def to_csv_row(self) -> list[str | int | float]:
        return [self.effect, self.bri]

    def is_effect_changed(self, other_variation: EffectVariation) -> bool:
        return self.effect != other_variation.effect

    @property
    def mode(self) -> LutMode:
        return LutMode.EFFECT


@dataclass
class LightModePlan:
    mode: LutMode
    variations: list[Variation]


@dataclass
class LightMeasurementPlan:
    modes: list[LightModePlan]
    effects: list[str]

    @property
    def variations(self) -> list[Variation]:
        return [variation for mode in self.modes for variation in mode.variations]

    @property
    def variation_count(self) -> int:
        return sum(len(mode.variations) for mode in self.modes)

    def for_mode(self, mode: LutMode) -> LightModePlan:
        return next(mode_plan for mode_plan in self.modes if mode_plan.mode == mode)


def build_light_plan(
    modes: Collection[LutMode],
    parameters: MeasurementParameters,
    light_info: LightInfo,
    effects: Sequence[str] | None = None,
) -> LightMeasurementPlan:
    """Build the ordered variations used by preflight and runtime execution."""

    mode_set = set(modes)
    effect_list = list(effects or [])
    return LightMeasurementPlan(
        modes=[
            LightModePlan(
                mode=mode,
                variations=_variations_for_mode(mode, parameters, light_info, effect_list),
            )
            for mode in LIGHT_MODE_ORDER
            if mode in mode_set
        ],
        effects=effect_list,
    )


def variation_from_csv_row(row: Sequence[str], mode: LutMode) -> Variation | None:
    """Parse a measurement CSV data row into its variation, or None when incomplete.

    A row only counts when every variation column parses and the power column holds
    a finite number, so torn rows from an interrupted write are never resumed from.
    """
    watt_index = len(CSV_HEADERS[mode]) - 1
    try:
        if len(row) <= watt_index or not math.isfinite(float(row[watt_index])):
            return None
        if mode == LutMode.BRIGHTNESS:
            return Variation(bri=int(row[0]))
        if mode == LutMode.COLOR_TEMP:
            return ColorTempVariation(bri=int(row[0]), ct=int(row[1]))
        if mode == LutMode.HS:
            return HsVariation(bri=int(row[0]), hue=int(row[1]), sat=int(row[2]))
        if mode == LutMode.EFFECT:
            return EffectVariation(effect=row[0], bri=int(row[1])) if row[0].strip() else None
    except ValueError:
        return None
    raise RunnerError(f"Mode {mode} not supported")


def variations_after(variations: Sequence[Variation], resume_at: Variation | None) -> list[Variation]:
    if resume_at is None:
        return list(variations)
    try:
        index = variations.index(resume_at)
    except ValueError:
        raise RunnerError(
            "The existing measurement CSV does not match the configured measurement grid; "
            "start a new session or restore the original settings to resume",
        ) from None
    return list(variations[index + 1 :])


def estimate_light_time_left(
    plan: LightMeasurementPlan,
    parameters: MeasurementParameters,
    *,
    current_mode: LutMode | None = None,
    remaining_variations: Sequence[Variation] | None = None,
    current_variation: Variation | None = None,
) -> float:
    """Return the runner's deterministic baseline estimate in seconds."""

    all_variations = plan.variations
    remaining = list(remaining_variations) if remaining_variations is not None else all_variations
    if not all_variations:
        return 0

    mode = current_mode or plan.modes[0].mode
    progress = len(all_variations) - len(remaining)
    step_time = _step_time(mode, parameters)

    time_left = 0.0
    if progress == 0:
        time_left += parameters.sleep_standby + parameters.sleep_initial
    time_left += len(remaining) * step_time
    time_left += _mode_transition_time(mode, current_variation, plan.effects, parameters)

    remaining_modes = {variation.mode for variation in remaining}
    time_left += sum(
        _mode_transition_time(remaining_mode, None, plan.effects, parameters)
        for remaining_mode in remaining_modes
        if remaining_mode != mode
    )
    return max(0.0, time_left)


def _variations_for_mode(
    mode: LutMode,
    parameters: MeasurementParameters,
    light_info: LightInfo,
    effects: list[str],
) -> list[Variation]:
    if mode == LutMode.BRIGHTNESS:
        return [
            Variation(bri=bri)
            for bri in _measurement_range(
                parameters,
                parameters.min_brightness,
                parameters.max_brightness,
                parameters.bri_bri_steps,
            )
        ]
    if mode == LutMode.COLOR_TEMP:
        min_mired = round(light_info.min_mired)
        max_mired = round(light_info.max_mired)
        return [
            ColorTempVariation(bri=bri, ct=mired)
            for bri in _measurement_range(
                parameters,
                parameters.min_brightness,
                parameters.max_brightness,
                parameters.ct_bri_steps,
            )
            for mired in _measurement_range(
                parameters,
                min_mired,
                max_mired,
                parameters.ct_mired_steps,
            )
        ]
    if mode == LutMode.HS:
        return [
            HsVariation(bri=bri, hue=hue, sat=sat)
            for bri in _measurement_range(
                parameters,
                parameters.min_brightness,
                parameters.max_brightness,
                parameters.hs_bri_steps,
            )
            for sat in _measurement_range(
                parameters,
                parameters.min_sat,
                parameters.max_sat,
                parameters.hs_sat_steps,
            )
            for hue in _measurement_range(
                parameters,
                parameters.min_hue,
                parameters.max_hue,
                parameters.hs_hue_steps,
            )
        ]
    if mode == LutMode.EFFECT:
        if not effects:
            raise RunnerError("No effects found for the light")
        return [
            EffectVariation(bri=bri, effect=effect)
            for effect in effects
            for bri in _measurement_range(
                parameters,
                max(parameters.min_brightness, 5),
                parameters.max_brightness,
                parameters.effect_bri_steps,
            )
        ]
    raise RunnerError(f"Mode {mode} not supported")


def _inclusive_range(start: int, end: int, step: int) -> list[int]:
    values = list(range(start, end, step))
    values.append(end)
    return values


def _measurement_range(parameters: MeasurementParameters, start: int, end: int, step: int) -> list[int]:
    if parameters.fast_test_mode:
        return [start] if start == end else [start, end]
    return _inclusive_range(start, end, step)


def _step_time(mode: LutMode, parameters: MeasurementParameters) -> float:
    if mode == LutMode.EFFECT:
        return parameters.measure_time_effect + ESTIMATED_IO_DELAY
    step_time = parameters.sleep_time + ESTIMATED_IO_DELAY
    if parameters.sample_count > 1:
        step_time += parameters.sample_count * (parameters.sleep_time_sample + ESTIMATED_IO_DELAY)
    return step_time


def _mode_transition_time(
    mode: LutMode,
    current_variation: Variation | None,
    effects: list[str],
    parameters: MeasurementParameters,
) -> float:
    if mode == LutMode.HS:
        hs_variation = current_variation if isinstance(current_variation, HsVariation) else None
        brightness = hs_variation.bri if hs_variation else parameters.min_brightness
        sat_steps_left = (
            round(
                (parameters.max_brightness - brightness) / parameters.hs_bri_steps,
            )
            - 1
        )
        time_left = sat_steps_left * parameters.sleep_time_sat
        hue_steps_left = round(parameters.max_hue / parameters.hs_hue_steps * sat_steps_left)
        return time_left + hue_steps_left * parameters.sleep_time_hue
    if mode == LutMode.COLOR_TEMP:
        ct_variation = current_variation if isinstance(current_variation, ColorTempVariation) else None
        brightness = ct_variation.bri if ct_variation else parameters.min_brightness
        ct_steps_left = (
            round(
                (parameters.max_brightness - brightness) / parameters.ct_bri_steps,
            )
            - 1
        )
        return ct_steps_left * parameters.sleep_time_ct
    if mode == LutMode.EFFECT:
        effect_variation = current_variation if isinstance(current_variation, EffectVariation) else None
        effect_progress = effects.index(effect_variation.effect) if effect_variation else 0
        return (len(effects) - effect_progress - 1) * parameters.sleep_time_effect_change
    return 0
