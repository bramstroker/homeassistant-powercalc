import os
from typing import Union

import homeassistant.helpers.entity_registry as er
from homeassistant.core import callback
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import HomeAssistantType


async def evaluate_power(power: Union[Template, float]) -> float:
    """When power is a template render it."""

    if isinstance(power, Template):
        return power.async_render()

    return power
