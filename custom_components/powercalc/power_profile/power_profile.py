from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import os
from typing import Any, cast

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.components.lawn_mower import DOMAIN as LAWN_MOWER_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    BUILT_IN_LIBRARY_DIR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_POWER,
    DOMAIN,
    CalculationStrategy,
    PowerProfileSource,
)
from custom_components.powercalc.errors import (
    ModelNotSupportedError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.power_profile.sub_profile_selector import SubProfileSelectConfig

_LOGGER = logging.getLogger(__name__)


class DeviceType(StrEnum):
    CAMERA = "camera"
    COVER = "cover"
    FAN = "fan"
    GENERIC_IOT = "generic_iot"
    LIGHT = "light"
    POWER_METER = "power_meter"
    PRINTER = "printer"
    SMART_DIMMER = "smart_dimmer"
    SMART_SWITCH = "smart_switch"
    SMART_SPEAKER = "smart_speaker"
    TELEVISION = "television"
    NETWORK = "network"
    VACUUM_ROBOT = "vacuum_robot"
    LAWN_MOWER_ROBOT = "lawn_mower_robot"


class DiscoveryBy(StrEnum):
    DEVICE = "device"
    ENTITY = "entity"


@dataclass(frozen=True)
class CustomField:
    key: str
    label: str
    selector: dict[str, Any]
    description: str | None = None


DEVICE_TYPE_DOMAIN: dict[DeviceType, str | set[str]] = {
    DeviceType.CAMERA: CAMERA_DOMAIN,
    DeviceType.COVER: COVER_DOMAIN,
    DeviceType.FAN: FAN_DOMAIN,
    DeviceType.GENERIC_IOT: {SENSOR_DOMAIN, MEDIA_PLAYER_DOMAIN},
    DeviceType.LIGHT: LIGHT_DOMAIN,
    DeviceType.POWER_METER: SENSOR_DOMAIN,
    DeviceType.SMART_DIMMER: LIGHT_DOMAIN,
    DeviceType.SMART_SWITCH: {SWITCH_DOMAIN, LIGHT_DOMAIN},
    DeviceType.SMART_SPEAKER: MEDIA_PLAYER_DOMAIN,
    DeviceType.TELEVISION: MEDIA_PLAYER_DOMAIN,
    DeviceType.NETWORK: BINARY_SENSOR_DOMAIN,
    DeviceType.PRINTER: SENSOR_DOMAIN,
    DeviceType.VACUUM_ROBOT: VACUUM_DOMAIN,
    DeviceType.LAWN_MOWER_ROBOT: LAWN_MOWER_DOMAIN,
}

SUPPORTED_DOMAINS: set[str] = {domain for domains in DEVICE_TYPE_DOMAIN.values() for domain in (domains if isinstance(domains, set) else {domains})}


def _build_domain_device_type_mapping() -> Mapping[str, set[DeviceType]]:
    """Get the device types for a given entity domain."""
    domain_to_device_type: defaultdict[str, set[DeviceType]] = defaultdict(set)
    for device_type, domains in DEVICE_TYPE_DOMAIN.items():
        domain_set = domains if isinstance(domains, set) else {domains}
        for domain in domain_set:
            domain_to_device_type[domain].add(device_type)
    return domain_to_device_type


DOMAIN_DEVICE_TYPE_MAPPING: Mapping[str, set[DeviceType]] = _build_domain_device_type_mapping()


class PowerProfile:
    def __init__(
        self,
        hass: HomeAssistant,
        manufacturer: str,
        model: str,
        directory: str,
        json_data: ConfigType,
    ) -> None:
        self._manufacturer = manufacturer
        self._model = model.replace("#slash#", "/")
        self._hass = hass
        self._directory = directory
        self._json_data = json_data
        self.sub_profile: str | None = None
        self._sub_profile_dir: str | None = None
        self._sub_profiles: list[tuple[str, dict]] | None = None

    def get_model_directory(self, root_only: bool = False) -> str:
        """Get the model directory containing the data files."""
        if root_only:
            return self._directory

        return self._sub_profile_dir or self._directory

    @property
    def manufacturer(self) -> str:
        """Get the manufacturer of this profile."""
        return self._manufacturer

    @property
    def model(self) -> str:
        """Get the model of this profile."""
        return self._model

    @property
    def unique_id(self) -> str:
        """Get the unique id of this profile."""
        return self._json_data.get("unique_id") or f"{self._manufacturer}_{self._model}"

    @property
    def name(self) -> str:
        """Get the name of this profile."""
        return self._json_data.get("name") or ""

    @property
    def json_data(self) -> ConfigType:
        """Get the raw json data."""
        return self._json_data

    @property
    def standby_power(self) -> float:
        """Get the standby power when the device is off."""
        return self._json_data.get("standby_power") or 0

    @property
    def standby_power_on(self) -> float:
        """Get the standby power (self usage) when the device is on."""
        standby_power_on = self._json_data.get("standby_power_on")
        if standby_power_on is None and self.only_self_usage:
            return self.standby_power
        return standby_power_on or 0

    @property
    def calculation_strategy(self) -> CalculationStrategy:
        """Get the calculation strategy this profile provides"""
        return CalculationStrategy(str(self._json_data.get("calculation_strategy", CalculationStrategy.LUT)))

    @property
    def linked_profile(self) -> str | None:
        """Get the linked profile."""
        return self._json_data.get("linked_profile", self._json_data.get("linked_lut"))

    @property
    def calculation_enabled_condition(self) -> str | None:
        """Get the condition to enable the calculation."""
        return self._json_data.get("calculation_enabled_condition")

    @property
    def aliases(self) -> list[str]:
        """Get a list of aliases for this model."""
        return self._json_data.get("aliases") or []

    @property
    def linear_config(self) -> ConfigType | None:
        """Get configuration to set up linear strategy."""
        config = self.get_strategy_config(CalculationStrategy.LINEAR)
        if config is None:
            return {CONF_MIN_POWER: 0, CONF_MAX_POWER: 0}
        return config

    @property
    def min_version(self) -> str | None:
        """Get the minimum required version for this profile."""
        return self._json_data.get("min_version")  # pragma: no cover

    @property
    def multi_switch_config(self) -> ConfigType | None:
        """Get configuration to set up multi_switch strategy."""
        return self.get_strategy_config(CalculationStrategy.MULTI_SWITCH)

    @property
    def fixed_config(self) -> ConfigType | None:
        """Get configuration to set up fixed strategy."""
        config = self.get_strategy_config(CalculationStrategy.FIXED)
        if config is None and self.standby_power_on:
            return {CONF_POWER: 0}
        return config

    @property
    def composite_config(self) -> list | None:
        """Get configuration to set up composite strategy."""
        return cast(list, self._json_data.get("composite_config"))

    @property
    def playbook_config(self) -> ConfigType | None:
        """Get configuration to set up playbook strategy."""
        return self.get_strategy_config(CalculationStrategy.PLAYBOOK)

    def get_strategy_config(self, strategy: CalculationStrategy) -> ConfigType | None:
        """Get configuration for a certain strategy."""
        if not self.is_strategy_supported(strategy):
            raise UnsupportedStrategyError(
                f"Strategy {strategy} is not supported by model: {self._model}",
            )
        return self._json_data.get(f"{strategy}_config")

    @property
    def sensor_config(self) -> ConfigType:
        """Additional sensor configuration."""
        return self._json_data.get("sensor_config") or {}

    def is_strategy_supported(self, mode: CalculationStrategy) -> bool:
        """Whether a certain calculation strategy is supported by this profile."""
        return mode == self.calculation_strategy

    @property
    def needs_fixed_config(self) -> bool:
        """Used for smart switches which only provides standby power values.
        This indicates the user must supply the power values in the config flow.
        """
        if self.only_self_usage:
            return False

        return self.is_strategy_supported(
            CalculationStrategy.FIXED,
        ) and not self._json_data.get("fixed_config")

    @property
    def needs_linear_config(self) -> bool:
        """
        Used for smart dimmers. This indicates the user must supply the power values in the config flow.
        """
        if self.only_self_usage:
            return False

        return self.is_strategy_supported(
            CalculationStrategy.LINEAR,
        ) and not self._json_data.get("linear_config")

    @property
    def device_type(self) -> DeviceType | None:
        """Get the device type of this profile."""
        device_type = self._json_data.get("device_type")
        if not device_type:
            return DeviceType.LIGHT
        try:
            return DeviceType(device_type)
        except ValueError:
            _LOGGER.warning("Unknown device type: %s", device_type)
            return None

    @property
    def discovery_by(self) -> DiscoveryBy:
        return DiscoveryBy(self._json_data.get("discovery_by", DiscoveryBy.ENTITY))

    @property
    def only_self_usage(self) -> bool:
        """Whether this profile only provides self usage."""
        return bool(self._json_data.get("only_self_usage", False))

    @property
    def has_custom_fields(self) -> bool:
        """Whether this profile has custom fields."""
        return bool(self._json_data.get("fields"))

    @property
    def custom_fields(self) -> list[CustomField]:
        """Get the custom fields of this profile."""
        return [CustomField(key=key, **field) for key, field in self._json_data.get("fields", {}).items()]

    @property
    def config_flow_discovery_remarks(self) -> str | None:
        """Get remarks to show at the config flow discovery step."""
        remarks = self._json_data.get("config_flow_discovery_remarks")
        if not remarks:
            translation_key = self.get_default_discovery_remarks_translation_key()
            if translation_key:
                translations = translation.async_get_cached_translations(
                    self._hass,
                    self._hass.config.language,
                    "common",
                    DOMAIN,
                )
                return translations.get(f"component.{DOMAIN}.common.{translation_key}")

        return remarks

    @property
    def config_flow_sub_profile_remarks(self) -> str | None:
        """Get extra remarks to show at the config flow sub profile step."""
        return self._json_data.get("config_flow_sub_profile_remarks")

    @property
    def compatible_integrations(self) -> list[str] | None:
        """Get the list of compatible integrations for this profile."""
        return self._json_data.get("compatible_integrations")

    def get_default_discovery_remarks_translation_key(self) -> str | None:
        """When no remarks are provided in the profile, see if we need to show a default remark."""
        if self.device_type == DeviceType.SMART_SWITCH and self.needs_fixed_config:
            return "remarks_smart_switch"
        if self.device_type == DeviceType.SMART_DIMMER and self.needs_linear_config:
            return "remarks_smart_dimmer"
        return None

    async def get_sub_profiles(self) -> list[tuple[str, dict]]:
        """Get listing of possible sub profiles and their corresponding JSON data."""

        if self._sub_profiles:
            return self._sub_profiles

        def _get_sub_dirs_and_json() -> list[tuple[str, dict]]:
            base_dir = self.get_model_directory(True)
            sub_dirs = next(os.walk(base_dir))[1]
            result = []
            for sub_dir in sub_dirs:
                json_path = os.path.join(base_dir, sub_dir, "model.json")
                if os.path.isfile(json_path):
                    with open(json_path, encoding="utf-8") as f:
                        json_data = json.load(f)
                else:
                    json_data = {}
                result.append((sub_dir, json_data))
            return result

        self._sub_profiles = sorted(
            await self._hass.async_add_executor_job(_get_sub_dirs_and_json),
            key=lambda x: x[0],  # Sort by directory name
        )
        return self._sub_profiles

    @property
    async def has_sub_profiles(self) -> bool:
        """Check whether this profile has sub profiles."""
        return len(await self.get_sub_profiles()) > 0

    @property
    async def requires_manual_sub_profile_selection(self) -> bool:
        """Check whether this profile requires manual sub profile selection."""
        if not await self.has_sub_profiles:
            return False

        return not self.has_sub_profile_select_matchers

    @property
    def sub_profile_select(self) -> SubProfileSelectConfig | None:
        """Get the configuration for automatic sub profile switching."""
        select_dict = self._json_data.get("sub_profile_select")
        if not select_dict:
            return None
        return SubProfileSelectConfig(**select_dict)

    @property
    def has_sub_profile_select_matchers(self) -> bool:
        """Check whether the sub profile select has matchers."""
        if not self.sub_profile_select:
            return False
        return bool(self.sub_profile_select.matchers)

    async def select_sub_profile(self, sub_profile: str) -> None:
        """Select a sub profile. Only applicable when to profile actually supports sub profiles."""
        if not await self.has_sub_profiles:
            return

        # Sub profile already selected, no need to load it again
        if self.sub_profile == sub_profile:
            return

        sub_profiles = await self.get_sub_profiles()
        found_profile = None
        for sub_dir, json_data in sub_profiles:
            if sub_dir == sub_profile:
                found_profile = json_data
                break

        if found_profile is None:
            raise ModelNotSupportedError(
                f"Sub profile not found (manufacturer: {self._manufacturer}, model: {self._model}, sub_profile: {sub_profile})",
            )

        self._sub_profile_dir = os.path.join(self._directory, sub_profile)
        _LOGGER.debug("Loading sub profile: %s", sub_profile)

        self._json_data.update(found_profile)

        self.sub_profile = sub_profile

    @property
    async def needs_user_configuration(self) -> bool:
        """Check whether this profile needs user configuration."""
        if self.calculation_strategy == CalculationStrategy.MULTI_SWITCH:
            return True

        if self.needs_fixed_config or self.needs_linear_config:
            return True

        if self.has_custom_fields:
            return True

        return await self.has_sub_profiles and not self.sub_profile_select

    def is_entity_domain_supported(self, entity_entry: RegistryEntry) -> bool:
        """Check whether this power profile supports a given entity domain."""
        if self.device_type is None:
            return False

        domain = entity_entry.domain

        # see https://github.com/bramstroker/homeassistant-powercalc/issues/2529
        if self.device_type == DeviceType.PRINTER and entity_entry.unit_of_measurement:
            return False

        return self.device_type in DOMAIN_DEVICE_TYPE_MAPPING[domain]

    @property
    def is_custom_profile(self) -> bool:
        """Whether this profile is a custom profile."""
        return not self._directory.startswith(self._hass.config.path(STORAGE_DIR, BUILT_IN_LIBRARY_DIR))

    @property
    def configuration_source(self) -> PowerProfileSource:
        return PowerProfileSource.LIBRARY_CUSTOM if self.is_custom_profile else PowerProfileSource.LIBRARY_BUILTIN
