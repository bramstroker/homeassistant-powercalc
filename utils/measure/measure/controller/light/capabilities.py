from collections.abc import Mapping, Sequence
import math
from typing import Any

from measure.controller.light.const import HASS_HS_COMPATIBLE_COLOR_MODES, MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo


def merge_light_infos(infos: Sequence[LightInfo]) -> LightInfo:
    """Reduce several lights to the color temperature range they all support."""

    if not infos:
        raise ValueError("Cannot merge an empty set of light infos")
    return LightInfo(
        "unknown",
        min_mired=max(info.min_mired for info in infos),
        max_mired=min(info.max_mired for info in infos),
    )


def common_effects(effect_lists: Sequence[Sequence[str]]) -> list[str]:
    """Effects every light offers, in the order the first light lists them."""

    if not effect_lists:
        return []
    first, *rest = effect_lists
    return [effect for effect in first if all(effect in other for other in rest)]


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
    modes: list[LutMode] = []
    if LutMode.BRIGHTNESS in values:
        modes.append(LutMode.BRIGHTNESS)
    if LutMode.COLOR_TEMP in values:
        modes.append(LutMode.COLOR_TEMP)
    if values & HASS_HS_COMPATIBLE_COLOR_MODES:
        modes.append(LutMode.HS)
    if attributes.get("effect_list"):
        modes.append(LutMode.EFFECT)
    return modes


def kelvin_to_mired(kelvin_temperature: float) -> int:
    return math.floor(1_000_000 / kelvin_temperature)


def mired_to_kelvin(mired_temperature: float) -> int:
    return math.floor(1_000_000 / mired_temperature)
