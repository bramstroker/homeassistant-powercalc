from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping
from csv import reader
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from functools import partial
import gzip
import logging
import os
from typing import Any, TextIO, TypeVar, cast

from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    COLOR_MODES_COLOR,
    ColorMode,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.util.color import color_temperature_kelvin_to_mired, color_temperature_to_hs

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.errors import (
    LutFileNotFoundError,
    StrategyConfigurationError,
)
from custom_components.powercalc.power_profile.power_profile import PowerProfile

from .strategy_interface import PowerCalculationStrategyInterface

_LOGGER = logging.getLogger(__name__)

BrightnessLutValue = float
ColorTempLutValue = dict[int, float]
SatLutValue = dict[int, float]
HsLutValue = dict[int, SatLutValue]
LookupDictValue = BrightnessLutValue | ColorTempLutValue | HsLutValue
LookupDictType = dict[int, LookupDictValue]
EffectTableType = dict[str, dict[int, float]]


class LookupMode(StrEnum):
    EFFECT = "effect"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"

    @staticmethod
    def from_color_mode(color_mode: ColorMode) -> LookupMode:
        return LookupMode(color_mode.value)


@dataclass
class _LutEntry:
    """Holds a lookup dictionary together with its pre-sorted brightness key list."""

    table: LookupDictType
    sorted_keys: list[int]


@dataclass
class _EffectEntry:
    """Holds an effect lookup table (str → {brightness: power})."""

    table: EffectTableType


class LutRegistry:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._lut_entries: dict[tuple, _LutEntry] = {}
        self._effect_entries: dict[tuple, _EffectEntry] = {}
        self._supported_modes: dict[tuple, set[LookupMode]] = {}

    async def get_lookup_entry(
        self,
        power_profile: PowerProfile,
        lookup_mode: LookupMode,
    ) -> _LutEntry:
        """Return a cached _LutEntry for the given profile and mode."""
        cache_key = self._cache_key(power_profile, lookup_mode)
        entry = self._lut_entries.get(cache_key)
        if entry is None:
            entry = await self._hass.async_add_executor_job(partial(self._load_lut_entry, power_profile, lookup_mode))
            self._lut_entries[cache_key] = entry
        return entry

    async def get_effect_entry(
        self,
        power_profile: PowerProfile,
    ) -> _EffectEntry:
        """Return a cached _EffectEntry for the given profile."""
        cache_key = self._cache_key(power_profile, LookupMode.EFFECT)
        entry = self._effect_entries.get(cache_key)
        if entry is None:
            entry = await self._hass.async_add_executor_job(partial(self._load_effect_entry, power_profile))
            self._effect_entries[cache_key] = entry
        return entry

    async def get_supported_modes(self, power_profile: PowerProfile) -> set[LookupMode]:
        """Return the LUT modes supported by the profile."""
        cache_key = (power_profile.manufacturer, power_profile.model, "supported_modes")
        supported_modes = self._supported_modes.get(cache_key)
        if supported_modes is None:
            supported_modes = set()
            for filename in await self._hass.async_add_executor_job(os.listdir, power_profile.get_model_directory()):
                if filename.endswith((".csv.gz", ".csv")):
                    base_name = filename.split(".", 1)[0]
                    supported_modes.add(LookupMode(base_name))
            self._supported_modes[cache_key] = supported_modes
        return supported_modes

    @staticmethod
    def _cache_key(power_profile: PowerProfile, lookup_mode: LookupMode) -> tuple:
        return power_profile.manufacturer, power_profile.model, lookup_mode, power_profile.sub_profile

    @classmethod
    def _load_lut_entry(cls, power_profile: PowerProfile, lookup_mode: LookupMode) -> _LutEntry:
        """Load a non-effect CSV into a typed _LutEntry."""
        raw: dict[int, Any] = {}

        csv_file = cls.get_lut_file(power_profile, lookup_mode)
        line_count = 0
        with csv_file:
            csv_reader = reader(csv_file)
            next(csv_reader)  # skip header row
            for row in csv_reader:
                if lookup_mode == LookupMode.HS:
                    bri_key = int(row[0])
                    hue_key = int(row[1])
                    sat_key = int(row[2])
                    raw.setdefault(bri_key, {}).setdefault(hue_key, {})[sat_key] = float(row[3])
                elif lookup_mode == LookupMode.COLOR_TEMP:
                    bri_key = int(row[0])
                    ct_key = int(row[1])
                    raw.setdefault(bri_key, {})[ct_key] = float(row[2])
                else:
                    raw[int(row[0])] = float(row[1])
                line_count += 1

        _LOGGER.debug("LUT file loaded: %d lines", line_count)
        table = cast(LookupDictType, raw)
        return _LutEntry(table=table, sorted_keys=sorted(table.keys()))

    @classmethod
    def _load_effect_entry(cls, power_profile: PowerProfile) -> _EffectEntry:
        """Load an effect CSV into a typed _EffectEntry."""
        raw: dict[str, dict[int, float]] = {}

        csv_file = cls.get_lut_file(power_profile, LookupMode.EFFECT)
        line_count = 0
        with csv_file:
            csv_reader = reader(csv_file)
            next(csv_reader)  # skip header row
            for row in csv_reader:
                effect_name: str = row[0]
                bri_key = int(row[1])
                raw.setdefault(effect_name, {})[bri_key] = float(row[2])
                line_count += 1

        _LOGGER.debug("Effect LUT file loaded: %d lines", line_count)
        return _EffectEntry(table=raw)

    @staticmethod
    def get_lut_file(power_profile: PowerProfile, lookup_mode: LookupMode) -> TextIO:
        """
        Open the LUT file for the given power profile and color mode.
        When the file is gzipped it will be decompressed transparently.
        """
        path = os.path.join(power_profile.get_model_directory(), f"{lookup_mode}.csv")

        gzip_path = f"{path}.gz"
        if os.path.exists(gzip_path):
            _LOGGER.debug("Loading LUT data file: %s", gzip_path)
            return gzip.open(gzip_path, "rt")

        if os.path.exists(path):
            _LOGGER.debug("Loading LUT data file: %s", path)
            return open(path)

        raise LutFileNotFoundError("Data file not found: %s")


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
        self._supported_modes: set[LookupMode] = set()
        self._effect_entry: _EffectEntry | None = None

    async def initialize(self) -> None:
        self._supported_modes = await self._lut_registry.get_supported_modes(self._profile)

    async def calculate(self, entity_state: State) -> Decimal | None:
        """Calculate the power consumption based on brightness, mired, hsl or effect."""
        attrs = entity_state.attributes

        brightness = attrs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            _LOGGER.error(
                "%s: Could not calculate power. no brightness set",
                entity_state.entity_id,
            )
            return None
        if brightness > 255:
            brightness = 255

        color_mode = await self.get_selected_color_mode(attrs)
        if color_mode == ColorMode.UNKNOWN:
            _LOGGER.warning(
                "%s: Could not calculate power. color mode unknown",
                entity_state.entity_id,
            )
            return None

        effect = attrs.get(ATTR_EFFECT)
        if effect and str(effect).lower() != "off":
            return await self._calculate_effect_power(entity_state, str(effect), brightness)

        lut_mode = LookupMode.from_color_mode(color_mode)

        try:
            lut_entry = await self._lut_registry.get_lookup_entry(self._profile, lut_mode)
        except LutFileNotFoundError:
            _LOGGER.error(
                "%s: Lookup table not found for color mode (model: %s, color_mode: %s)",
                entity_state.entity_id,
                self._profile.model,
                color_mode,
            )
            return None

        light_setting = self.create_light_setting(entity_state, color_mode, brightness)
        if light_setting is None:
            return None

        _LOGGER.debug(
            "%s: Looking up power usage with settings: %s",
            entity_state.entity_id,
            {attr: getattr(light_setting, attr) for attr in vars(light_setting)},
        )

        power = self.lookup_power(lut_entry, light_setting)
        _LOGGER.debug("%s: Calculated power:%s", entity_state.entity_id, power)
        return Decimal(power)

    async def _calculate_effect_power(
        self,
        entity_state: State,
        effect: str,
        brightness: int,
    ) -> Decimal | None:
        """Look up power for an active light effect."""
        if LookupMode.EFFECT not in self._supported_modes:
            _LOGGER.warning("%s: Effects not supported for this power profile", entity_state.entity_id)
            return None

        effect_entry = await self._lut_registry.get_effect_entry(self._profile)
        effect_table = effect_entry.table.get(effect)
        if effect_table is None:
            _LOGGER.warning('%s: Effect "%s" not found in LUT', entity_state.entity_id, effect)
            return None

        sorted_keys = sorted(effect_table.keys())
        return Decimal(self._interpolate(effect_table, sorted_keys, brightness))

    def create_light_setting(
        self,
        entity_state: State,
        color_mode: ColorMode,
        brightness: int,
    ) -> LightSetting | None:
        """Create a LightSetting object based on the entity state."""
        light_setting = LightSetting(color_mode=color_mode, brightness=brightness)

        attrs = entity_state.attributes
        if color_mode == ColorMode.COLOR_TEMP:
            color_temp = attrs.get(ATTR_COLOR_TEMP_KELVIN)
            if color_temp is None:
                _LOGGER.error(
                    "%s: Could not calculate power. no color temp set. Please check the attributes of your light in the developer tools.",
                    entity_state.entity_id,
                )
                return None
            light_setting.color_temp = color_temperature_kelvin_to_mired(color_temp)
            return light_setting

        if color_mode == ColorMode.HS:
            try:
                original_color_mode = attrs.get(ATTR_COLOR_MODE)
                hs = color_temperature_to_hs(attrs[ATTR_COLOR_TEMP_KELVIN]) if original_color_mode == ColorMode.COLOR_TEMP else attrs[ATTR_HS_COLOR]
                light_setting.hue = int(hs[0] / 360 * 65535)
                light_setting.saturation = int(hs[1] / 100 * 255)
            except Exception:  # noqa: BLE001
                _LOGGER.error(
                    "%s: Could not calculate power. no hue/sat set. Please check the attributes of your light in the developer tools.",
                    entity_state.entity_id,
                )
                return None

        return light_setting

    async def get_selected_color_mode(self, attrs: Mapping[str, Any]) -> ColorMode:
        """Get the selected color mode for the entity."""
        try:
            color_mode = ColorMode(str(attrs.get(ATTR_COLOR_MODE, ColorMode.UNKNOWN)))
        except ValueError:
            color_mode = ColorMode.UNKNOWN
        if color_mode == ColorMode.WHITE:
            return ColorMode.BRIGHTNESS
        if color_mode == ColorMode.UNKNOWN:
            return color_mode
        if color_mode in COLOR_MODES_COLOR:
            color_mode = ColorMode.HS
        lookup_mode = LookupMode.from_color_mode(color_mode)
        if lookup_mode not in self._supported_modes and color_mode == ColorMode.COLOR_TEMP:
            _LOGGER.debug("Color mode not natively supported, falling back to HS")
            color_mode = ColorMode.HS
        return color_mode

    @staticmethod
    def _nearest_key(sorted_keys: list[int], x: int) -> int:
        """Return the key in sorted_keys nearest to x."""
        i = bisect_left(sorted_keys, x)
        if i == 0:
            return sorted_keys[0]
        if i >= len(sorted_keys):
            return sorted_keys[-1]
        before = sorted_keys[i - 1]
        after = sorted_keys[i]
        return before if (x - before) <= (after - x) else after

    @staticmethod
    def _interpolate(table: dict[int, float], sorted_keys: list[int], brightness: int) -> float:
        """Linear interpolation over a flat {brightness: power} table."""
        if brightness in table:
            return table[brightness]

        i = bisect_left(sorted_keys, brightness)
        if i == 0:
            return table[sorted_keys[0]]
        if i >= len(sorted_keys):
            return table[sorted_keys[-1]]

        b0 = sorted_keys[i - 1]
        b1 = sorted_keys[i]
        p0 = table[b0]
        p1 = table[b1]
        return p0 + (p1 - p0) * ((brightness - b0) / (b1 - b0))

    def lookup_power(
        self,
        lut_entry: _LutEntry,
        light_setting: LightSetting,
    ) -> float:
        lookup_table = lut_entry.table
        sorted_keys = lut_entry.sorted_keys
        brightness = light_setting.brightness

        # Exact brightness match — skip interpolation entirely.
        if brightness in lookup_table:
            return self.lookup_power_for_brightness(lookup_table[brightness], light_setting)

        i = bisect_left(lut_entry.sorted_keys, brightness)

        if i == 0:
            return self.lookup_power_for_brightness(lookup_table[sorted_keys[0]], light_setting)
        if i >= len(sorted_keys):
            return self.lookup_power_for_brightness(lookup_table[sorted_keys[-1]], light_setting)

        b0 = sorted_keys[i - 1]
        b1 = sorted_keys[i]
        p0 = self.lookup_power_for_brightness(lookup_table[b0], light_setting)
        p1 = self.lookup_power_for_brightness(lookup_table[b1], light_setting)
        return p0 + (p1 - p0) * ((brightness - b0) / (b1 - b0))

    def lookup_power_for_brightness(
        self,
        lut_value: LookupDictValue,
        light_setting: LightSetting,
    ) -> float:
        if isinstance(lut_value, float):
            return lut_value

        if light_setting.color_mode == ColorMode.COLOR_TEMP:
            return self.get_nearest(lut_value, light_setting.color_temp or 0)  # type: ignore

        # HS path — outer dict is hue → {saturation → power}
        hs_table = cast(HsLutValue, lut_value)
        sat_values = self.get_nearest(hs_table, light_setting.hue or 0)
        return self.get_nearest(sat_values, light_setting.saturation or 0)

    # Generic nearest lookup for both float values and nested saturation dicts
    _NearestT = TypeVar("_NearestT", float, dict[int, float])

    def get_nearest(self, lookup_dict: dict[int, _NearestT], search_key: int) -> _NearestT:
        """Return the value mapped at search_key or the nearest neighbour key."""
        value = lookup_dict.get(search_key)
        if value is not None:
            return value
        nearest = self._nearest_key(sorted(lookup_dict.keys()), search_key)
        return lookup_dict[nearest]

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
    effect: str | None = None
