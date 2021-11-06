"""Utilities for auto discovery of light models."""

from __future__ import annotations

import logging
import os
import re
from collections import namedtuple
from typing import NamedTuple, Optional

import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.components.light import Light
from homeassistant.helpers.typing import HomeAssistantType

from .common import SourceEntity
from .const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
    MANUFACTURER_ALIASES,
)
from .light_model import LightModel

_LOGGER = logging.getLogger(__name__)


async def get_light_model(
    hass: HomeAssistantType, source_entity: SourceEntity, config: dict
) -> Optional[LightModel]:
    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)
    if manufacturer is None or model is None:
        model_info = await autodiscover_model(hass, source_entity)
        if model_info:
            manufacturer = model_info.manufacturer
            model = model_info.model

    if manufacturer is None or model is None:
        return None

    custom_model_directory = config.get(CONF_CUSTOM_MODEL_DIRECTORY)
    if custom_model_directory:
        custom_model_directory = os.path.join(
            hass.config.config_dir, custom_model_directory
        )

    return LightModel(hass, manufacturer, model, custom_model_directory)


async def autodiscover_model(
    hass: HomeAssistantType, source_entity: SourceEntity
) -> Optional[ModelInfo]:
    """Try to auto discover manufacturer and model from the known device information"""

    entity_entry = source_entity.entity_entry
    if entity_entry is None:
        return None

    device_registry = await dr.async_get_registry(hass)
    device_entry = device_registry.async_get(entity_entry.device_id)
    if device_entry is None:
        return None

    if device_entry.manufacturer is None or device_entry.model is None:
        _LOGGER.error(
            "%s: Cannot autodiscover model, manufacturer or model unknown from device registry",
            entity_entry.entity_id,
        )
        return None

    model_id = device_entry.model
    match = re.search("\((.*)\)$", device_entry.model)
    if match:
        model_id = match.group(1)

    manufacturer = device_entry.manufacturer
    if MANUFACTURER_ALIASES.get(manufacturer):
        manufacturer = MANUFACTURER_ALIASES.get(manufacturer)

    model_info = ModelInfo(manufacturer, model_id)

    # This check can be removed in future version
    if match is None and entity_entry.platform == "hue":
        model_info = await autodiscover_from_hue_bridge(hass, entity_entry)
        if model_info is None:
            return None

    _LOGGER.debug(
        "%s: Auto discovered model (manufacturer=%s, model=%s)",
        entity_entry.entity_id,
        model_info.manufacturer,
        model_info.model,
    )
    return model_info


async def autodiscover_from_hue_bridge(
    hass: HomeAssistantType, entity_entry: er.RegistryEntry
):
    # Code below is for BC purposes. Will be removed in a future version
    light = await find_hue_light(hass, entity_entry)
    if light is None:
        _LOGGER.error(
            "%s: Cannot autodiscover model, not found in the hue bridge api",
            entity_entry.entity_id,
        )
        return None

    return ModelInfo(light.manufacturername, light.modelid)


async def find_hue_light(
    hass: HomeAssistantType, entity_entry: er.RegistryEntry
) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""

    bridge = hass.data["hue"][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if light.uniqueid == entity_entry.unique_id:
            return light

    return None


class ModelInfo(NamedTuple):
    manufacturer: str
    model: str
