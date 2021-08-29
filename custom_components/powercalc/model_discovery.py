"""Utilities for auto discovery of light models."""

from __future__ import annotations

import logging
import os
from collections import namedtuple
from typing import NamedTuple, Optional

import homeassistant.helpers.entity_registry as er
from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from homeassistant.components.light import Light
from homeassistant.helpers.typing import HomeAssistantType

from .const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_MANUFACTURER, CONF_MODEL
from .light_model import LightModel

_LOGGER = logging.getLogger(__name__)


async def get_light_model(
    hass: HomeAssistantType, entity_entry, config: dict
) -> Optional[LightModel]:
    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)
    if (manufacturer is None or model is None) and entity_entry:
        hue_model_info = await autodiscover_hue_model(hass, entity_entry)
        if hue_model_info:
            manufacturer = hue_model_info.manufacturer
            model = hue_model_info.model

    if manufacturer is None or model is None:
        return None

    custom_model_directory = config.get(CONF_CUSTOM_MODEL_DIRECTORY)
    if custom_model_directory:
        custom_model_directory = os.path.join(
            hass.config.config_dir, custom_model_directory
        )

    return LightModel(manufacturer, model, custom_model_directory)


async def autodiscover_hue_model(
    hass: HomeAssistantType, entity_entry
) -> Optional[HueModelInfo]:
    # When Philips Hue model is enabled we can auto discover manufacturer and model from the bridge data
    if hass.data.get(HUE_DOMAIN) is None or entity_entry.platform != "hue":
        return

    light = await find_hue_light(hass, entity_entry)
    if light is None:
        _LOGGER.error(
            "Cannot autodiscover model for '%s', not found in the hue bridge api",
            entity_entry.entity_id,
        )
        return

    _LOGGER.debug(
        "Auto discovered Hue model for entity %s: (manufacturer=%s, model=%s)",
        entity_entry.entity_id,
        light.manufacturername,
        light.modelid,
    )

    return HueModelInfo(light.manufacturername, light.modelid)


async def find_hue_light(
    hass: HomeAssistantType, entity_entry: er.RegistryEntry
) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""

    bridge = hass.data[HUE_DOMAIN][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if light.uniqueid == entity_entry.unique_id:
            return light

    return None


class HueModelInfo(NamedTuple):
    manufacturer: str
    model: str
