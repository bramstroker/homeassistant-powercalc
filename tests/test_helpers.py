from decimal import Decimal

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.powercalc.helpers import evaluate_power


@pytest.mark.parametrize(
    "power,output",
    [
        (Template("unknown"), None),
        (Template("{{ 1 + 3 | float }}"), Decimal(4.0)),
        (20.5, Decimal(20.5)),
        ("foo", None),
        (Decimal(40.65), Decimal(40.65)),
    ],
)
async def test_evaluate_power(
    hass: HomeAssistant, power: Template | Decimal | float, output: Decimal | None
) -> None:
    if isinstance(power, Template):
        power.hass = hass
    assert await evaluate_power(power) == output
