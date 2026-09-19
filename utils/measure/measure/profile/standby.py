"""Standby validation and suggestions from measured library profiles."""

from dataclasses import dataclass
from enum import StrEnum
import math
from statistics import median
from typing import TypeGuard

MINIMUM_STANDBY_POWER = 0.05
STANDBY_UNAVAILABLE_WARNING = (
    "Standby power could not be measured reliably. Your light measurements are saved. "
    "Enter a separately measured standby value or use an estimate before submitting."
)


def is_valid_standby_power(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= MINIMUM_STANDBY_POWER
    )


class StandbyEstimateBasis(StrEnum):
    MANUFACTURER = "manufacturer"
    CONNECTIVITY = "connectivity"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class StandbyEstimate:
    power_w: float = 0.4
    basis: StandbyEstimateBasis = StandbyEstimateBasis.FALLBACK
    profile_count: int = 0


def estimate_standby_power(library: object, manufacturer: str, connectivity: list[str]) -> StandbyEstimate:
    """Use matching measured lights, preferring at least three from the same manufacturer."""
    if not connectivity or not isinstance(library, dict):
        return StandbyEstimate()
    manufacturers = library.get("manufacturers")
    if not isinstance(manufacturers, list):
        return StandbyEstimate()
    matching_power: list[float] = []
    manufacturer_power: list[float] = []
    seen: set[tuple[str, str]] = set()
    for entry in manufacturers:
        if not isinstance(entry, dict) or not isinstance(entry.get("models"), list):
            continue
        name = str(entry.get("full_name") or entry.get("name") or "")
        directory = str(entry.get("dir_name") or name)
        for model in _matching_models(entry["models"], connectivity):
            identity = (directory, str(model["id"]))
            if identity in seen:
                continue
            seen.add(identity)
            value = model["standby_power"]
            assert is_valid_standby_power(value)
            power = float(value)
            matching_power.append(power)
            if name.casefold() == manufacturer.casefold():
                manufacturer_power.append(power)
    if len(manufacturer_power) >= 3:
        return StandbyEstimate(
            round(median(manufacturer_power), 2), StandbyEstimateBasis.MANUFACTURER, len(manufacturer_power)
        )
    if len(matching_power) >= 3:
        return StandbyEstimate(round(median(matching_power), 2), StandbyEstimateBasis.CONNECTIVITY, len(matching_power))
    return StandbyEstimate()


def _matching_models(models: list[object], connectivity: list[str]) -> list[dict[str, object]]:
    matching = []
    for model in models:
        if not isinstance(model, dict) or model.get("device_type") != "light":
            continue
        if not model.get("id") or not is_valid_standby_power(model.get("standby_power")):
            continue
        if model.get("standby_power_estimated") is True:
            continue
        specs = model.get("device_specs")
        if not isinstance(specs, dict):
            continue
        connections = specs.get("connectivity")
        if not isinstance(connections, list) or not all(isinstance(value, str) for value in connections):
            continue
        if set(connections) == set(connectivity):
            matching.append(model)
    return matching
