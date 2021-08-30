from __future__ import annotations

import gzip
import logging
import os
from collections import defaultdict
from csv import reader
from functools import partial
from typing import Optional

from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODES_COLOR,
)
from homeassistant.core import State

from .common import SourceEntity
from .errors import (
    LutFileNotFound,
    ModelNotSupported,
    StrategyConfigurationError,
    UnsupportedMode,
)
from .light_model import LightModel
from .strategy_interface import PowerCalculationStrategyInterface

LUT_COLOR_MODES = {COLOR_MODE_BRIGHTNESS, COLOR_MODE_COLOR_TEMP, COLOR_MODE_HS}

_LOGGER = logging.getLogger(__name__)


class LutRegistry:
    def __init__(self) -> None:
        self._lookup_dictionaries = {}

    async def get_lookup_dictionary(
        self, light_model: LightModel, color_mode: str
    ) -> dict | None:
        cache_key = f"{light_model.manufacturer}_{light_model.model}_{color_mode}"
        lookup_dict = self._lookup_dictionaries.get(cache_key)
        if lookup_dict is None:
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)

            with self.get_lut_file(light_model, color_mode) as csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader)  # skip header row

                for row in csv_reader:
                    if color_mode == COLOR_MODE_HS:
                        lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(
                            row[3]
                        )
                    elif color_mode == COLOR_MODE_COLOR_TEMP:
                        lookup_dict[int(row[0])][int(row[1])] = float(row[2])
                    elif color_mode == COLOR_MODE_BRIGHTNESS:
                        lookup_dict[int(row[0])] = float(row[1])
                    else:
                        raise UnsupportedMode(f"Unsupported color mode {color_mode}")

            lookup_dict = dict(lookup_dict)
            self._lookup_dictionaries[cache_key] = lookup_dict

        return lookup_dict

    def get_lut_file(self, light_model: LightModel, color_mode: str):
        path = os.path.join(light_model.get_directory(), f"{color_mode}.csv")

        gzip_path = f"{path}.gz"
        if os.path.exists(gzip_path):
            _LOGGER.debug("Loading data file: %s", gzip_path)
            return gzip.open(gzip_path, "rt")

        elif os.path.exists(path):
            _LOGGER.debug("Loading data file: %s", path)
            return open(path, "r")

        raise LutFileNotFound("Data file not found: %s")


class LutStrategy(PowerCalculationStrategyInterface):
    def __init__(self, lut_registry: LutRegistry, model: LightModel) -> None:
        self._lut_registry = lut_registry
        self._model = model

    async def calculate(self, entity_state: State) -> Optional[int]:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        attrs = entity_state.attributes
        color_mode = attrs.get(ATTR_COLOR_MODE)
        if color_mode in COLOR_MODES_COLOR:
            color_mode = COLOR_MODE_HS

        brightness = attrs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            _LOGGER.error("No brightness for entity: %s", entity_state.entity_id)
            return None
        if brightness > 255:
            brightness = 255

        try:
            lookup_table = await self._lut_registry.get_lookup_dictionary(
                self._model, color_mode
            )
        except LutFileNotFound:
            _LOGGER.error("Lookup table not found")
            return None

        power = 0
        if color_mode == COLOR_MODE_HS:
            hs = attrs[ATTR_HS_COLOR]
            hue = int(hs[0] / 360 * 65535)
            sat = int(hs[1] / 100 * 255)
            _LOGGER.debug(
                "Looking up power usage for bri:%s hue:%s sat:%s}", brightness, hue, sat
            )
            hue_values = self.get_closest_from_dictionary(lookup_table, brightness)
            sat_values = self.get_closest_from_dictionary(hue_values, hue)
            power = self.get_closest_from_dictionary(sat_values, sat)
        elif color_mode == COLOR_MODE_COLOR_TEMP:
            mired = attrs[ATTR_COLOR_TEMP]
            _LOGGER.debug(
                "Looking up power usage for bri:%s mired:%s", brightness, mired
            )
            mired_values = self.get_closest_from_dictionary(lookup_table, brightness)
            power = self.get_closest_from_dictionary(mired_values, mired)
        elif color_mode == COLOR_MODE_BRIGHTNESS:
            _LOGGER.debug("Looking up power usage for bri:%s", brightness)
            power = self.get_closest_from_dictionary(lookup_table, brightness)

        _LOGGER.debug("Power:%s", power)
        return power

    def get_closest_from_dictionary(self, dict: dict, search_key):
        return (
            dict.get(search_key)
            or dict[min(dict.keys(), key=lambda key: abs(key - search_key))]
        )

    def get_nearest_lower(self, dict: dict, search_key):
        return (
            dict.get(search_key)
            or dict[min(dict.keys(), key=lambda key: abs(key - search_key))]
        )

    async def validate_config(self, source_entity: SourceEntity):
        if source_entity.domain != light.DOMAIN:
            raise StrategyConfigurationError("Only light entities can use the LUT mode")

        if self._model.manufacturer is None:
            _LOGGER.error(
                "Manufacturer not supplied for entity: %s", source_entity.entity_id
            )

        if self._model.model is None:
            _LOGGER.error("Model not supplied for entity: %s", source_entity.entity_id)
            return

        supported_color_modes = source_entity.capabilities[
            light.ATTR_SUPPORTED_COLOR_MODES
        ]
        for color_mode in supported_color_modes:
            if color_mode in LUT_COLOR_MODES:
                try:
                    await self._lut_registry.get_lookup_dictionary(
                        self._model, color_mode
                    )
                except LutFileNotFound:
                    raise ModelNotSupported("No lookup file found for mode", color_mode)
