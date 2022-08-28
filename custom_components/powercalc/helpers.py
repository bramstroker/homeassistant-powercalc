from decimal import Decimal
from typing import Union

from homeassistant.helpers.template import Template


async def evaluate_power(power: Union[Template, Decimal, float]) -> Decimal:
    """When power is a template render it."""

    if isinstance(power, Template):
        return power.async_render()

    return Decimal(power)
