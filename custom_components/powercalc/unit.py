"""Shared helpers for parsing numeric state values and converting between units."""

from __future__ import annotations

from decimal import Decimal, DecimalException

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    PowerConverter,
)

from custom_components.powercalc.const import UnitPrefix

# Maps a configured energy unit prefix to the resulting energy unit of measurement.
ENERGY_UNIT_PREFIX_MAPPING: dict[str, str] = {
    UnitPrefix.NONE: UnitOfEnergy.WATT_HOUR,
    UnitPrefix.KILO: UnitOfEnergy.KILO_WATT_HOUR,
    UnitPrefix.MEGA: UnitOfEnergy.MEGA_WATT_HOUR,
    UnitPrefix.GIGA: UnitOfEnergy.GIGA_WATT_HOUR,
    UnitPrefix.TERA: UnitOfEnergy.TERA_WATT_HOUR,
}

# Maps any energy or power unit of measurement to the converter that handles it.
UNIT_CONVERTERS: dict[str | None, type[BaseUnitConverter]] = {
    **dict.fromkeys(EnergyConverter.VALID_UNITS, EnergyConverter),
    **dict.fromkeys(PowerConverter.VALID_UNITS, PowerConverter),
}


def parse_decimal(value: object) -> Decimal | None:
    """Parse a numeric value into a Decimal, returning None when it is not a usable number.

    Accepts a Home Assistant State (its ``state`` string is used) or a raw value of any type.
    Unknown or unavailable states and values that are not numeric yield None instead of raising.
    """
    if isinstance(value, State):
        if value.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        value = value.state
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        return Decimal(value)
    except DecimalException, ValueError:
        return None


def convert_to_decimal(
    value: State | str | float | Decimal,
    from_unit: str | None,
    to_unit: str | None,
) -> Decimal | None:
    """Convert a value between energy/power units and return it as a Decimal.

    Returns None when the value is not numeric or the units cannot be converted.
    """
    parsed = parse_decimal(value)
    if parsed is None:
        return None
    if from_unit == to_unit:
        return parsed
    converter = UNIT_CONVERTERS.get(from_unit)
    if converter is None:
        return None
    try:
        return Decimal(str(converter.convert(float(parsed), from_unit, to_unit)))
    except HomeAssistantError:
        return None
