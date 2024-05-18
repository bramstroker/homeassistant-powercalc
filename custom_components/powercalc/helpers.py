import decimal
import logging
import os.path
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
        _LOGGER.error("Could not convert power value %s to decimal", power)
        return None


def get_library_path(sub_path: str = "") -> str:
    """Get the path to the library file."""
    base_path = os.path.join(os.path.dirname(__file__), "../../profile_library")
    return f"{base_path}/{sub_path}"


def get_library_json_path() -> str:
    """Get the path to the library.json file."""
    return get_library_path("library.json")
