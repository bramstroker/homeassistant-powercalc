import decimal
import logging
from decimal import Decimal
from typing import Union

from homeassistant.helpers.template import Template

_LOGGER = logging.getLogger(__name__)


async def evaluate_power(power: Union[Template, Decimal, float]) -> Decimal | None:
    """When power is a template render it."""

    try:
        if isinstance(power, Template):
            return Decimal(power.async_render())

        return Decimal(power)
    except decimal.DecimalException:
        _LOGGER.error(f"Could not convert power value {power} to decimal")
