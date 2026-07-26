from decimal import Decimal

from homeassistant.const import STATE_UNAVAILABLE, UnitOfEnergy, UnitOfPower
from homeassistant.core import State
import pytest

from custom_components.powercalc.unit import convert_to_decimal


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        # Successful conversions
        (1, UnitOfEnergy.WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, Decimal("0.001")),
        (1, UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.WATT_HOUR, Decimal("1000.0")),
        ("50", UnitOfPower.WATT, UnitOfPower.KILO_WATT, Decimal("0.05")),
        (State("sensor.test", "1000"), UnitOfPower.WATT, UnitOfPower.KILO_WATT, Decimal("1.0")),
        # Identical units are returned as-is, without consulting a converter
        (Decimal("12.5"), UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, Decimal("12.5")),
        ("12.5", None, None, Decimal("12.5")),
        # Non numeric values
        ("foo", UnitOfEnergy.WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, None),
        (None, UnitOfEnergy.WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, None),
        (State("sensor.test", STATE_UNAVAILABLE), UnitOfPower.WATT, UnitOfPower.KILO_WATT, None),
        # No converter known for the source unit
        (10, "bogus", UnitOfEnergy.KILO_WATT_HOUR, None),
        (10, None, UnitOfEnergy.KILO_WATT_HOUR, None),
        # Converter exists, but cannot handle the target unit
        (10, UnitOfEnergy.WATT_HOUR, UnitOfPower.WATT, None),
    ],
)
async def test_convert_to_decimal(
    value: State | str | float | Decimal,
    from_unit: str | None,
    to_unit: str | None,
    expected: Decimal | None,
) -> None:
    assert convert_to_decimal(value, from_unit, to_unit) == expected
