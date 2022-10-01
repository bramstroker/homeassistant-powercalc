from __future__ import annotations

import gzip
import logging
import os
from collections import defaultdict
from csv import reader
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import Optional, Union

import numpy as np
from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    COLOR_MODES_COLOR,
    ColorMode,
)
from homeassistant.core import State

from ..common import SourceEntity
from ..errors import LutFileNotFound, ModelNotSupported, StrategyConfigurationError
from ..power_profile.power_profile import PowerProfile
from .strategy_interface import PowerCalculationStrategyInterface

LUT_COLOR_MODES = {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS}

_LOGGER = logging.getLogger(__name__)


class LutRegistry:
    def __init__(self) -> None:
        self._lookup_dictionaries = {}

    async def get_lookup_dictionary(
        self, power_profile: PowerProfile, color_mode: str
    ) -> dict | None:
        cache_key = f"{power_profile.manufacturer}_{power_profile.model}_{color_mode}"
        lookup_dict = self._lookup_dictionaries.get(cache_key)
        if lookup_dict is None:
            defaultdict_of_dict = partial(defaultdict, dict)
            lookup_dict = defaultdict(defaultdict_of_dict)

            with self.get_lut_file(power_profile, color_mode) as csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader)  # skip header row

                line_count = 0
                for row in csv_reader:
                    if color_mode == ColorMode.HS:
                        lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(
                            row[3]
                        )
                    elif color_mode == ColorMode.COLOR_TEMP:
                        lookup_dict[int(row[0])][int(row[1])] = float(row[2])
                    else:
                        lookup_dict[int(row[0])] = float(row[1])
                    line_count += 1

            _LOGGER.debug("LUT file loaded: %d lines", line_count)

            lookup_dict = dict(lookup_dict)
            self._lookup_dictionaries[cache_key] = lookup_dict

        return lookup_dict

    def get_lut_file(self, power_profile: PowerProfile, color_mode: ColorMode):
        path = os.path.join(power_profile.get_model_directory(), f"{color_mode}.csv")

        gzip_path = f"{path}.gz"
        if os.path.exists(gzip_path):
            _LOGGER.debug("Loading LUT data file: %s", gzip_path)
            return gzip.open(gzip_path, "rt")

        raise LutFileNotFound("Data file not found: %s")


class LutStrategy(PowerCalculationStrategyInterface):
    def __init__(
        self,
        source_entity: SourceEntity,
        lut_registry: LutRegistry,
        profile: PowerProfile,
    ) -> None:
        self._source_entity = source_entity
        self._lut_registry = lut_registry
        self._profile = profile

    async def calculate(self, entity_state: State) -> Optional[Decimal]:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        attrs = entity_state.attributes
        color_mode = attrs.get(ATTR_COLOR_MODE)
        if color_mode in COLOR_MODES_COLOR:
            color_mode = ColorMode.HS

        brightness = attrs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            _LOGGER.error(
                "%s: Could not calculate power. no brightness set",
                entity_state.entity_id,
            )
            return None
        if brightness > 255:
            brightness = 255

        if color_mode == ColorMode.UNKNOWN:
            _LOGGER.debug(
                "%s: Could not calculate power. color mode unknown",
                entity_state.entity_id,
            )
            return None

        try:
            lookup_table = await self._lut_registry.get_lookup_dictionary(
                self._profile, color_mode
            )
        except LutFileNotFound:
            _LOGGER.error(
                "%s: Lookup table not found (model: %s, color_mode: %s)",
                entity_state.entity_id,
                self._profile.model,
                color_mode,
            )
            return None

        light_setting = LightSetting(color_mode=color_mode, brightness=brightness)
        if color_mode == ColorMode.HS:
            hs = attrs[ATTR_HS_COLOR]
            light_setting.hue = int(hs[0] / 360 * 65535)
            light_setting.saturation = int(hs[1] / 100 * 255)
            _LOGGER.debug(
                "%s: Looking up power usage for bri:%s hue:%s sat:%s}",
                entity_state.entity_id,
                brightness,
                light_setting.hue,
                light_setting.saturation,
            )
        elif color_mode == ColorMode.COLOR_TEMP:
            light_setting.color_temp = attrs[ATTR_COLOR_TEMP]
            _LOGGER.debug(
                "%s: Looking up power usage for bri:%s mired:%s",
                entity_state.entity_id,
                brightness,
                light_setting.color_temp,
            )
        elif color_mode == ColorMode.BRIGHTNESS:
            _LOGGER.debug(
                "%s: Looking up power usage for bri:%s",
                entity_state.entity_id,
                brightness,
            )

        power = Decimal(self.lookup_power(lookup_table, light_setting))
        _LOGGER.debug("%s: Calculated power:%s", entity_state.entity_id, power)
        return power

    def lookup_power(self, lookup_table: dict, light_setting: LightSetting) -> float:
        brightness = light_setting.brightness
        brightness_table = lookup_table.get(brightness)

        # Check if we have an exact match for the selected brightness level in de LUT
        if brightness_table:
            return self.lookup_power_for_brightness(brightness_table, light_setting)

        # We don't have an exact match, use interpolation
        brightness_range = [
            self.get_nearest_lower_brightness(lookup_table, brightness),
            self.get_nearest_higher_brightness(lookup_table, brightness),
        ]
        power_range = [
            self.lookup_power_for_brightness(
                lookup_table[brightness_range[0]], light_setting
            ),
            self.lookup_power_for_brightness(
                lookup_table[brightness_range[1]], light_setting
            ),
        ]
        return np.interp(brightness, brightness_range, power_range)

    def lookup_power_for_brightness(
        self, lut_value: Union[dict, int], light_setting: LightSetting
    ):
        if light_setting.color_mode == ColorMode.BRIGHTNESS:
            return lut_value
        if light_setting.color_mode == ColorMode.COLOR_TEMP:
            return self.get_nearest(lut_value, light_setting.color_temp)
        else:
            sat_values = self.get_nearest(lut_value, light_setting.hue)
            return self.get_nearest(sat_values, light_setting.saturation)

    @staticmethod
    def get_nearest(dict: dict, search_key: int):
        return (
            dict.get(search_key)
            or dict[min(dict.keys(), key=lambda key: abs(key - search_key))]
        )

    @staticmethod
    def get_nearest_lower_brightness(dict: dict, search_key: int) -> int:
        keys = dict.keys()
        last_key = [*keys][-1]
        if last_key < search_key:
            return last_key

        return max(
            (k for k in dict.keys() if int(k) <= int(search_key)), default=[*keys][0]
        )

    @staticmethod
    def get_nearest_higher_brightness(dict: dict, search_key: int) -> int:
        keys = dict.keys()
        first_key = [*keys][0]
        if first_key > search_key:
            return first_key

        return min((k for k in keys if int(k) >= int(search_key)), default=[*keys][-1])

    async def validate_config(self):
        if self._source_entity.domain != light.DOMAIN:
            raise StrategyConfigurationError(
                "Only light entities can use the LUT mode", "lut_unsupported_color_mode"
            )

        for color_mode in self._source_entity.supported_color_modes:
            if color_mode in LUT_COLOR_MODES:
                try:
                    await self._lut_registry.get_lookup_dictionary(
                        self._profile, color_mode
                    )
                except LutFileNotFound:
                    raise ModelNotSupported(
                        f"No lookup file found for mode: {color_mode}",
                        "lut_unsupported_color_mode",
                    )


@dataclass
class LightSetting:
    color_mode: ColorMode
    brightness: int
    hue: Optional[int] = None
    saturation: Optional[int] = None
    color_temp: Optional[int] = None
