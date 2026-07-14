from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo


def light_info_from_attributes(attributes: Mapping[str, Any]) -> LightInfo:
    """Translate Home Assistant light attributes into runner capabilities."""

    min_mired = MIN_MIRED
    if kelvin := attributes.get("max_color_temp_kelvin"):
        min_mired = kelvin_to_mired(float(kelvin))
    max_mired = MAX_MIRED
    if kelvin := attributes.get("min_color_temp_kelvin"):
        max_mired = kelvin_to_mired(float(kelvin))
    return LightInfo("unknown", min_mired, max_mired)


def supported_light_modes(attributes: Mapping[str, Any]) -> list[LutMode]:
    values = set(attributes.get("supported_color_modes", []))
    modes = [mode for mode in (LutMode.COLOR_TEMP, LutMode.HS) if mode.value in values]
    if values - {"onoff"} or "brightness" in attributes:
        modes.insert(0, LutMode.BRIGHTNESS)
    if attributes.get("effect_list"):
        modes.append(LutMode.EFFECT)
    return modes


def kelvin_to_mired(kelvin_temperature: float) -> int:
    return math.floor(1_000_000 / kelvin_temperature)


def mired_to_kelvin(mired_temperature: float) -> int:
    return math.floor(1_000_000 / mired_temperature)
