from __future__ import annotations

import os

from homeassistant.core import HomeAssistant

from ..const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_MANUFACTURER, CONF_MODEL
from ..errors import ModelNotSupported
from .library import ModelInfo, ProfileLibrary
from .power_profile import PowerProfile


async def get_power_profile(
    hass: HomeAssistant,
    config: dict,
    model_info: ModelInfo = None,
) -> PowerProfile | None:
    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)
    if (manufacturer is None or model is None) and model_info:
        manufacturer = config.get(CONF_MANUFACTURER) or model_info.manufacturer
        model = config.get(CONF_MODEL) or model_info.model

    if not manufacturer or not model:
        return None

    custom_model_directory = config.get(CONF_CUSTOM_MODEL_DIRECTORY)
    if custom_model_directory:
        custom_model_directory = os.path.join(
            hass.config.config_dir, custom_model_directory
        )

    library = ProfileLibrary.factory(hass)
    profile = await library.get_profile(
        ModelInfo(manufacturer, model), custom_model_directory
    )
    if profile is None:
        raise ModelNotSupported(
            f"Model not found in library (manufacturer: {manufacturer}, model: {model})"
        )
    return profile
