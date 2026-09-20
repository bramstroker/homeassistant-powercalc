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
    manufacturers = _library_manufacturers(library)
    if not connectivity or manufacturers is None:
        return StandbyEstimate()
    matching_power, manufacturer_power = _collect_matching_power(manufacturers, manufacturer, connectivity)
    if len(manufacturer_power) >= 3:
        return StandbyEstimate(
            round(median(manufacturer_power), 2), StandbyEstimateBasis.MANUFACTURER, len(manufacturer_power)
        )
    if len(matching_power) >= 3:
        return StandbyEstimate(round(median(matching_power), 2), StandbyEstimateBasis.CONNECTIVITY, len(matching_power))
    return StandbyEstimate()


def _library_manufacturers(library: object) -> list[object] | None:
    if not isinstance(library, dict):
        return None
    manufacturers = library.get("manufacturers")
    return manufacturers if isinstance(manufacturers, list) else None


def _collect_matching_power(
    manufacturers: list[object],
    manufacturer: str,
    connectivity: list[str],
) -> tuple[list[float], list[float]]:
    matching_power: list[float] = []
    manufacturer_power: list[float] = []
    seen: set[tuple[str, str]] = set()
    for entry in manufacturers:
        details = _manufacturer_models(entry)
        if details is None:
            continue
        name, directory, models = details
        for model in _matching_models(models, connectivity):
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
    return matching_power, manufacturer_power


def _manufacturer_models(entry: object) -> tuple[str, str, list[object]] | None:
    if not isinstance(entry, dict):
        return None
    models = entry.get("models")
    if not isinstance(models, list):
        return None
    name = str(entry.get("full_name") or entry.get("name") or "")
    directory = str(entry.get("dir_name") or name)
    return name, directory, models


def _matching_models(models: list[object], connectivity: list[str]) -> list[dict[str, object]]:
    return [model for model in models if _is_matching_model(model, connectivity)]


def _is_matching_model(model: object, connectivity: list[str]) -> TypeGuard[dict[str, object]]:
    if not isinstance(model, dict):
        return False
    if model.get("device_type") != "light":
        return False
    if not model.get("id"):
        return False
    if not is_valid_standby_power(model.get("standby_power")):
        return False
    if model.get("standby_power_estimated") is True:
        return False
    specs = model.get("device_specs")
    if not isinstance(specs, dict):
        return False
    connections = specs.get("connectivity")
    if not isinstance(connections, list):
        return False
    if not all(isinstance(value, str) for value in connections):
        return False
    return set(connections) == set(connectivity)
