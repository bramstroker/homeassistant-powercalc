from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import NamedTuple, Protocol

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.typing import ConfigType

from ..const import CalculationStrategy
from ..errors import ModelNotSupported, PowercalcSetupError, UnsupportedMode

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    LIGHT = "light"
    SMART_SWITCH = "smart_switch"
    SMART_SPEAKER = "smart_speaker"


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
        self._model = model.replace("#slash#", "/")
        self._hass = hass
        self._directory = directory
        self._json_data = json_data
        self.sub_profile: str | None = None
        self._sub_profile_dir: str | None = None

    def select_sub_profile(self, sub_profile: str) -> None:
        """Load the model.json file data containing information about the light model"""

        if not self.has_sub_profiles:
            return None

        # Sub profile already selected, no need to load it again
        if self.sub_profile == sub_profile:
            return None

        self._sub_profile_dir = os.path.join(self._directory, sub_profile)
        _LOGGER.debug(f"Loading sub profile directory {sub_profile}")
        if not os.path.exists(self._sub_profile_dir):
            raise ModelNotSupported(
                f"Sub profile not found (manufacturer: {self._manufacturer}, model: {self._model}, sub_profile: {sub_profile})"
            )

        # When the sub LUT directory also has a model.json (not required), merge this json into the main model.json data.
        file_path = os.path.join(self._sub_profile_dir, "model.json")
        if os.path.exists(file_path):
            json_file = open(file_path)
            self._json_data = {**self._json_data, **json.load(json_file)}

        self.sub_profile = sub_profile

    def get_model_directory(self, root_only: bool = False) -> str:
        if self.linked_lut:
            return os.path.join(os.path.dirname(__file__), "../data", self.linked_lut)

        if root_only:
            return self._directory

        return self._sub_profile_dir or self._directory

    def get_sub_profiles(self) -> list[str]:
        """Get listing op possible sub profiles"""
        return sorted(next(os.walk(self.get_model_directory(True)))[1])

    def supports(self, model: str) -> bool:
        """
        Check whether this power profile supports a given model ID.
        Also looks at possible aliases
        """
        model = model.lower().replace("#slash#", "/")

        if self._model.lower() == model:
            return True

        # @todo implement Regex/Json path
        for alias in self.aliases:
            if alias.lower() == model:
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
        return self._json_data.get("supported_modes") or [CalculationStrategy.LUT]

    @property
    def linked_lut(self) -> str | None:
        return self._json_data.get("linked_lut")

    @property
    def calculation_enabled_condition(self) -> str | None:
        return self._json_data.get("calculation_enabled_condition")

    @property
    def aliases(self) -> list[str]:
        return self._json_data.get("aliases") or []

    @property
    def linear_mode_config(self) -> ConfigType | None:
        if not self.is_mode_supported(CalculationStrategy.LINEAR):
            raise UnsupportedMode(
                f"Mode linear is not supported by model: {self._model}"
            )
        return self._json_data.get("linear_config")

    @property
    def fixed_mode_config(self) -> ConfigType | None:
        if not self.is_mode_supported(CalculationStrategy.FIXED):
            raise UnsupportedMode(
                f"Mode fixed is not supported by model: {self._model}"
            )
        return self._json_data.get("fixed_config")

    @property
    def sensor_config(self) -> ConfigType:
        return self._json_data.get("sensor_config") or {}

    def is_mode_supported(self, mode: str) -> bool:
        return mode in self.supported_modes

    @property
    def is_additional_configuration_required(self) -> bool:
        if (
            self.has_sub_profiles
            and self.sub_profile is None
            and self.sub_profile_select is None
        ):
            return True
        return self._json_data.get("requires_additional_configuration") or False

    @property
    def device_type(self) -> str:
        return self._json_data.get("device_type") or DeviceType.LIGHT

    @property
    def has_sub_profiles(self) -> bool:
        return len(self.get_sub_profiles()) > 0

    @property
    def sub_profile_select(self) -> SubProfileSelectConfig | None:
        select_dict = self._json_data.get("sub_profile_select")
        if not select_dict:
            return None
        return SubProfileSelectConfig(**select_dict)

    def is_entity_domain_supported(self, domain: str) -> bool:
        """Check whether this power profile supports a given entity domain"""
        if self.device_type == DeviceType.LIGHT and domain != LIGHT_DOMAIN:
            return False

        if (
            self.device_type == DeviceType.SMART_SPEAKER
            and domain != MEDIA_PLAYER_DOMAIN
        ):
            return False

        if self.device_type == DeviceType.SMART_SWITCH and domain != SWITCH_DOMAIN:
            return False

        return True


class SubProfileSelector:
    def select_sub_profile(
        self, power_profile: PowerProfile, entity_state: State
    ) -> str:
        """
        Dynamically tries to select a sub profile depending on the entity state.
        This method always need to return a sub profile, when nothing is matched it will return a default
        """
        select_config = power_profile.sub_profile_select
        if not select_config:
            raise PowercalcSetupError(
                "Cannot dynamically select sub profile, no `sub_profile_select` defined in model.json"
            )

        for matcher_config in select_config.matchers:
            matcher = self.create_matcher(matcher_config)
            sub_profile = matcher.match(entity_state)
            if sub_profile:
                return sub_profile

        return select_config.default

    @staticmethod
    def create_matcher(matcher_config: dict) -> SubProfileMatcher:
        """Create a matcher from json config. Can be extended for more matches in the future"""
        return AttributeMatcher(matcher_config["attribute"], matcher_config["map"])


class SubProfileSelectConfig(NamedTuple):
    default: str
    matchers: list[dict]


class SubProfileMatcher(Protocol):
    def match(self, entity_state: State) -> str | None:
        pass


class AttributeMatcher(SubProfileMatcher):
    def __init__(self, attribute: str, mapping: dict[str, str]):
        self._attribute = attribute
        self._mapping = mapping
        pass

    def match(self, entity_state: State) -> str | None:
        val = entity_state.attributes.get(self._attribute)
        if val is None:
            return None

        return self._mapping.get(val)
