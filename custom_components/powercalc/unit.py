"""Shared helpers for parsing numeric state values and converting between units."""

from __future__ import annotations

from decimal import Decimal, DecimalException
import logging

from homeassistant.const import UnitOfEnergy
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers.template import Template
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    PowerConverter,
)

from custom_components.powercalc.const import UNAVAILABLE_STATES, UnitPrefix

_LOGGER = logging.getLogger(__name__)

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
        if value.state in UNAVAILABLE_STATES:
            return None
        value = value.state
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        return Decimal(value)
    except DecimalException, ValueError:
        return None


def evaluate_to_decimal(value: object) -> Decimal | None:
    """Evaluate a value into a Decimal, rendering it first when it is a template.

    Non-template values (strings, numbers) are parsed directly. Returns None when a template
    fails to render, or when the (rendered) value is not a usable number. Unknown/unavailable
    renders yield None silently; any other failure is logged.
    """
    if isinstance(value, Template):
        try:
            value = value.async_render()
        except TemplateError as ex:
            _LOGGER.error("Could not render template %s: %s", value, ex)
            return None
        if value in UNAVAILABLE_STATES:
            return None

    result = parse_decimal(value)
    if result is None:
        _LOGGER.error("Could not convert value %s to a decimal", value)
    return result


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
