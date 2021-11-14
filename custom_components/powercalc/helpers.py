import os
from typing import Union
from homeassistant.core import callback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import HomeAssistantType

from homeassistant.helpers.template import Template

async def evaluate_power(power: Union[Template, float]) -> float:
    """When power is a template render it."""

    if isinstance(power, Template):
        return power.async_render()

    return power

