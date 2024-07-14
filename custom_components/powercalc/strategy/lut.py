from __future__ import annotations

import gzip
import io
import logging
import os
from collections import defaultdict
from collections.abc import Mapping
from csv import reader
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import Any

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
from homeassistant.core import HomeAssistant, State
from homeassistant.util.color import color_temperature_to_hs

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.errors import (
    LutFileNotFoundError,
    StrategyConfigurationError,
)
from custom_components.powercalc.power_profile.power_profile import PowerProfile

from .strategy_interface import PowerCalculationStrategyInterface

LUT_COLOR_MODES = {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS}

_LOGGER = logging.getLogger(__name__)

BrightnessLutType = dict[int, float]
ColorTempLutType = dict[int, dict[int, float]]
HsLutType = dict[int, dict[int, dict[int, float]]]
LookupDictType = BrightnessLutType | ColorTempLutType | HsLutType


class LutRegistry:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._lookup_dictionaries: dict[str, dict] = {}
        self._supported_color_modes: dict[str, set[ColorMode]] = {}

    async def get_lookup_dictionary(
        self,
        power_profile: PowerProfile,
        color_mode: ColorMode,
    ) -> LookupDictType:
        cache_key = f"{power_profile.manufacturer}_{power_profile.model}_{color_mode}_{power_profile.sub_profile}"
        lookup_dict = self._lookup_dictionaries.get(cache_key)
        if lookup_dict is None:
            defaultdict_of_dict = partial(defaultdict, dict)  # type: ignore[var-annotated]
            lookup_dict = defaultdict(defaultdict_of_dict)

            csv_file = await self._hass.async_add_executor_job(partial(self.get_lut_file, power_profile, color_mode))
            with csv_file:
                csv_reader = reader(csv_file)
                next(csv_reader)  # skip header row

                line_count = 0
                for row in csv_reader:
                    if color_mode == ColorMode.HS:
                        lookup_dict[int(row[0])][int(row[1])][int(row[2])] = float(
                            row[3],
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

    @staticmethod
    def get_lut_file(power_profile: PowerProfile, color_mode: ColorMode) -> io.TextIOWrapper:
        path = os.path.join(power_profile.get_model_directory(), f"{color_mode}.csv")

        gzip_path = f"{path}.gz"
        if os.path.exists(gzip_path):
            _LOGGER.debug("Loading LUT data file: %s", gzip_path)
            return gzip.open(gzip_path, "rt")  # type: ignore

        raise LutFileNotFoundError("Data file not found: %s")

    async def get_supported_color_modes(self, power_profile: PowerProfile) -> set[ColorMode]:
        """Return the color modes supported by the Profile."""
        cache_key = f"{power_profile.manufacturer}_{power_profile.model}_supported_color_modes"
        supported_color_modes = self._supported_color_modes.get(cache_key)
        if supported_color_modes is None:
            supported_color_modes = set()
            for file in await self._hass.async_add_executor_job(os.listdir, power_profile.get_model_directory()):
                if file.endswith(".csv.gz"):
                    color_mode = ColorMode(file.removesuffix(".csv.gz"))
                    if color_mode in LUT_COLOR_MODES:
                        supported_color_modes.add(color_mode)
            self._supported_color_modes[cache_key] = supported_color_modes
        return supported_color_modes


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
        self._strategy_color_modes: set[ColorMode] | None = None

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate the power consumption based on brightness, mired, hsl values."""
        attrs = entity_state.attributes
        original_color_mode = attrs.get(ATTR_COLOR_MODE)
        color_mode = await self.get_selected_color_mode(attrs)

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
            _LOGGER.warning(
                "%s: Could not calculate power. color mode unknown",
                entity_state.entity_id,
            )
            return None

        try:
            lookup_table = await self._lut_registry.get_lookup_dictionary(
                self._profile,
                color_mode,
            )
        except LutFileNotFoundError:
            _LOGGER.error(
                "%s: Lookup table not found for color mode (model: %s, color_mode: %s)",
                entity_state.entity_id,
                self._profile.model,
                color_mode,
            )
            return None

        light_setting = LightSetting(color_mode=color_mode, brightness=brightness)
        if color_mode == ColorMode.HS:
            try:
                hs = color_temperature_to_hs(attrs[ATTR_COLOR_TEMP]) if original_color_mode == ColorMode.COLOR_TEMP else attrs[ATTR_HS_COLOR]
                light_setting.hue = int(hs[0] / 360 * 65535)
                light_setting.saturation = int(hs[1] / 100 * 255)
                _LOGGER.debug(
                    "%s: Looking up power usage for bri:%s hue:%s sat:%s}",
                    entity_state.entity_id,
                    brightness,
                    light_setting.hue,
                    light_setting.saturation,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.error(
                    "%s: Could not calculate power. no hue/sat set. Please check the attributes of your light in the developer tools.",
                    entity_state.entity_id,
                )
                return None
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

    async def get_selected_color_mode(self, attrs: Mapping[str, Any]) -> ColorMode:
        """Get the selected color mode for the entity."""
        try:
            color_mode = ColorMode(str(attrs.get(ATTR_COLOR_MODE, ColorMode.UNKNOWN)))
        except ValueError:
            color_mode = ColorMode.UNKNOWN
        if color_mode in COLOR_MODES_COLOR:
            color_mode = ColorMode.HS
        profile_color_modes = await self._lut_registry.get_supported_color_modes(self._profile)
        if color_mode not in profile_color_modes and color_mode == ColorMode.COLOR_TEMP:
            _LOGGER.debug("Color mode not natively supported, falling back to HS")
            color_mode = ColorMode.HS
        return color_mode

    def lookup_power(
        self,
        lookup_table: LookupDictType,
        light_setting: LightSetting,
    ) -> float:
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
                lookup_table[brightness_range[0]],
                light_setting,
            ),
            self.lookup_power_for_brightness(
                lookup_table[brightness_range[1]],
                light_setting,
            ),
        ]
        return float(np.interp(brightness, brightness_range, power_range))

    def lookup_power_for_brightness(
        self,
        lut_value: LookupDictType | float,
        light_setting: LightSetting,
    ) -> float:
        if light_setting.color_mode == ColorMode.BRIGHTNESS:
            return lut_value  # type: ignore

        if not isinstance(lut_value, dict):  # pragma: no cover
            _LOGGER.warning(
                "Cannot calculate power for LutStrategy, expecting a dictionary",
            )
            return 0

        if light_setting.color_mode == ColorMode.COLOR_TEMP:
            return self.get_nearest(lut_value, light_setting.color_temp or 0)  # type: ignore

        sat_values = self.get_nearest(lut_value, light_setting.hue or 0)
        return self.get_nearest(sat_values, light_setting.saturation or 0)  # type: ignore

    @staticmethod
    def get_nearest(
        lookup_dict: LookupDictType,
        search_key: int,
    ) -> float | LookupDictType:
        return lookup_dict.get(search_key) or lookup_dict[min(lookup_dict.keys(), key=lambda key: abs(key - search_key))]

    @staticmethod
    def get_nearest_lower_brightness(
        lookup_dict: LookupDictType,
        search_key: int,
    ) -> int:
        keys = lookup_dict.keys()
        last_key = [*keys][-1]
        if last_key < search_key:
            return int(last_key)

        return max(
            (k for k in lookup_dict if int(k) <= int(search_key)),
            default=next(iter(keys)),
        )

    @staticmethod
    def get_nearest_higher_brightness(
        lookup_dict: LookupDictType,
        search_key: int,
    ) -> int:
        keys = lookup_dict.keys()
        first_key = next(iter(keys))
        if first_key > search_key:
            return int(first_key)

        return min((k for k in keys if int(k) >= int(search_key)), default=[*keys][-1])

    async def validate_config(self) -> None:
        if self._source_entity.domain != light.DOMAIN:
            raise StrategyConfigurationError(
                "Only light entities can use the LUT mode",
                "lut_unsupported_color_mode",
            )


@dataclass
class LightSetting:
    color_mode: ColorMode
    brightness: int
    hue: int | None = None
    saturation: int | None = None
    color_temp: int | None = None
