import decimal
import logging
from decimal import Decimal

from homeassistant.helpers.template import Template

_LOGGER = logging.getLogger(__name__)


async def evaluate_power(power: Template | Decimal | float) -> Decimal | None:
    """When power is a template render it."""

    if isinstance(power, Decimal):
        return power

    try:
        if isinstance(power, Template):
            power = power.async_render()
            if power == "unknown":
                return None

        return Decimal(power)  # type: ignore[arg-type]
    except decimal.DecimalException:
        _LOGGER.error(f"Could not convert power value {power} to decimal")
        return None
