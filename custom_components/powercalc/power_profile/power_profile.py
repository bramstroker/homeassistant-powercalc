from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Optional

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.core import HomeAssistant
from sqlalchemy import ForeignKey

from ..aliases import MODEL_DIRECTORY_MAPPING
from ..const import CalculationStrategy
from ..errors import ModelNotSupported, UnsupportedMode

_LOGGER = logging.getLogger(__name__)

class DeviceType(Enum):
    LIGHT = "light"
    SMART_SWITCH = "smart_switch"


class PowerProfile:
    def __init__(
        self,
        hass: HomeAssistant,
        manufacturer: str,
        model: str,
        directory: str | None,
        json_data: dict | None = None,
    ):
        self._manufacturer = manufacturer
        self._model = model
        self._hass = hass
        self._directory = directory
        self._json_data = json_data
        self.sub_profile: str | None = None
        self._sub_profile_dir: str | None = None

        self._model = self._model.replace("#slash#", "/")

    def load_sub_profile(self, sub_profile: str) -> None:
        """Load the model.json file data containing information about the light model"""

        self._sub_profile_dir = os.path.join(self._directory, sub_profile)
        _LOGGER.debug(f"Loading sub LUT directory {sub_profile}")
        if not os.path.exists(self._sub_profile_dir):
            raise ModelNotSupported(
                f"LUT subdirectory not found (manufacturer: {self._manufacturer}, model: {self._model})"
            )

        # When the sub LUT directory also has a model.json (not required), merge this json into the main model.json data.
        file_path = os.path.join(self._sub_profile_dir, "model.json")
        if os.path.exists(file_path):
            json_file = open(file_path)
            self._json_data = {**self._json_data, **json.load(json_file)}
        
        self.sub_profile = sub_profile

    def get_lut_directory(self) -> str:
        if self.linked_lut:
            return os.path.join(os.path.dirname(__file__), "../data", self.linked_lut)

        return self._sub_profile_dir or self._directory

    def supports(self, model: str) -> bool:
        if self._model == model:
            return True

        #@todo implement Regex/Json path
        for alias in self.aliases:
            if alias == model:
                return True
        
        return False

    @property
    def manufacturer(self) -> str:
        return self._manufacturer

    @property
    def model(self) -> str:
        return self._model

    @property
    def name(self) -> str:
        return self._json_data.get("name")

    @property
    def standby_power(self) -> float:
        return self._json_data.get("standby_power") or 0

    @property
    def standby_power_on(self) -> float:
        return self._json_data.get("standby_power_on") or 0

    @property
    def supported_modes(self) -> list:
        return self._json_data.get("supported_modes") or []

    @property
    def linked_lut(self) -> Optional[str]:
        return self._json_data.get("linked_lut")

    @property
    def calculation_enabled_condition(self) -> Optional[str]:
        return self._json_data.get("calculation_enabled_condition")

    @property
    def aliases(self) -> list:
        aliases = self._json_data.get("aliases") or []

        # Logic below can be removed when all aliases have been moved to model.json
        if self.manufacturer in MODEL_DIRECTORY_MAPPING: 
            aliases.extend(
                [
                    alias for (alias, model) 
                    in MODEL_DIRECTORY_MAPPING[self.manufacturer].items() 
                    if model == self.model
                ]
            )

        return aliases

    @property
    def linear_mode_config(self) -> Optional[dict]:
        if not self.is_mode_supported(CalculationStrategy.LINEAR):
            raise UnsupportedMode(
                f"Mode linear is not supported by model: {self._model}"
            )
        return self._json_data.get("linear_config")

    @property
    def fixed_mode_config(self) -> Optional[dict]:
        if not self.is_mode_supported(CalculationStrategy.FIXED):
            raise UnsupportedMode(
                f"Mode fixed is not supported by model: {self._model}"
            )
        return self._json_data.get("fixed_config")

    def is_mode_supported(self, mode: str) -> bool:
        return mode in self.supported_modes

    @property
    def is_additional_configuration_required(self) -> bool:
        if self.sub_profile is not None:
            return True
        return self._json_data.get("requires_additional_configuration") or False

    @property
    def device_type(self) -> str:
        return self._json_data.get("device_type") or DeviceType.LIGHT

    def is_entity_domain_supported(self, domain: str) -> bool:
        """Check whether this power profile supports a given entity domain"""
        if domain == LIGHT_DOMAIN and self.device_type != DeviceType.LIGHT:
            return False

        return True
