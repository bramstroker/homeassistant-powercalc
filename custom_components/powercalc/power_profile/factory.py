from __future__ import annotations

import logging
import os

from homeassistant.core import HomeAssistant

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_VARIABLES,
    MANUFACTURER_WLED,
)
from custom_components.powercalc.errors import ModelNotSupportedError

from .error import LibraryError
from .library import ModelInfo, ProfileLibrary
from .power_profile import PowerProfile

_LOGGER = logging.getLogger(__name__)


async def get_power_profile(
    hass: HomeAssistant,
    config: dict,
    source_entity: SourceEntity | None = None,
    model_info: ModelInfo | None = None,
    log_errors: bool = True,
    process_variables: bool = True,
) -> PowerProfile | None:
    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)
    model_id = None
    if (manufacturer is None or model is None) and model_info:
        manufacturer = config.get(CONF_MANUFACTURER) or model_info.manufacturer
        model = config.get(CONF_MODEL) or model_info.model
        model_id = model_info.model_id

    custom_model_directory = config.get(CONF_CUSTOM_MODEL_DIRECTORY)

    if (not manufacturer or not model) and not custom_model_directory:
        return None

    if manufacturer == MANUFACTURER_WLED:
        return None

    if custom_model_directory:
        custom_model_directory = os.path.join(
            hass.config.config_dir,
            custom_model_directory,
        )

    library = await ProfileLibrary.factory(hass)
    try:
        variables = config.get(CONF_VARIABLES, {}).copy()
        profile = await library.get_profile(
            ModelInfo(manufacturer or "", model or "", model_id),
            source_entity,
            custom_model_directory,
            variables,
            process_variables,
        )
    except LibraryError as err:
        if log_errors:
            _LOGGER.error("Problem loading model: %s", err)
        raise ModelNotSupportedError(
            f"Model not found in library (manufacturer: {manufacturer}, model: {model})",
        ) from err

    return profile
