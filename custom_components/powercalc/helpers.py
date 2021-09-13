import os
from typing import Union

from homeassistant.helpers.template import Template

from custom_components.powercalc import LightModel

from .const import MANUFACTURER_DIRECTORY_MAPPING


def get_light_model_directory(light_model: LightModel) -> str:
    manufacturer_directory = (
        MANUFACTURER_DIRECTORY_MAPPING.get(light_model.manufacturer)
        or light_model.manufacturer
    )

    return os.path.join(
        os.path.dirname(__file__), f"data/{manufacturer_directory}/{light_model.model}"
    )


async def evaluate_power(power: Union[Template, float]) -> float:
    """When power is a template render it."""

    if isinstance(power, Template):
        return power.async_render()

    return power
