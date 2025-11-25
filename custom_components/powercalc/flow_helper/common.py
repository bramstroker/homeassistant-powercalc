from collections.abc import Callable, Coroutine
import copy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import voluptuous as vol


class Step(StrEnum):
    ADVANCED_OPTIONS = "advanced_options"
    ASSIGN_GROUPS = "assign_groups"
    AVAILABILITY_ENTITY = "availability_entity"
    BASIC_OPTIONS = "basic_options"
    GROUP_CUSTOM = "group_custom"
    GROUP_DOMAIN = "group_domain"
    GROUP_SUBTRACT = "group_subtract"
    GROUP_TRACKED_UNTRACKED = "group_tracked_untracked"
    GROUP_TRACKED_UNTRACKED_AUTO = "group_tracked_untracked_auto"
    GROUP_TRACKED_UNTRACKED_MANUAL = "group_tracked_untracked_manual"
    LIBRARY = "library"
    POST_LIBRARY = "post_library"
    LIBRARY_CUSTOM_FIELDS = "library_custom_fields"
    LIBRARY_MULTI_PROFILE = "library_multi_profile"
    LIBRARY_OPTIONS = "library_options"
    VIRTUAL_POWER = "virtual_power"
    FIXED = "fixed"
    LINEAR = "linear"
    MULTI_SWITCH = "multi_switch"
    PLAYBOOK = "playbook"
    WLED = "wled"
    POWER_ADVANCED = "power_advanced"
    DAILY_ENERGY = "daily_energy"
    REAL_POWER = "real_power"
    MANUFACTURER = "manufacturer"
    MENU_LIBRARY = "menu_library"
    MENU_GROUP = "menu_group"
    MODEL = "model"
    SUB_PROFILE = "sub_profile"
    USER = "user"
    SMART_SWITCH = "smart_switch"
    INIT = "init"
    ENERGY_OPTIONS = "energy_options"
    UTILITY_METER_OPTIONS = "utility_meter_options"
    GLOBAL_CONFIGURATION = "global_configuration"
    GLOBAL_CONFIGURATION_DISCOVERY = "global_configuration_discovery"
    GLOBAL_CONFIGURATION_ENERGY = "global_configuration_energy"
    GLOBAL_CONFIGURATION_THROTTLING = "global_configuration_throttling"
    GLOBAL_CONFIGURATION_UTILITY_METER = "global_configuration_utility_meter"


class FlowType(StrEnum):
    VIRTUAL_POWER = "virtual_power"
    DAILY_ENERGY = "daily_energy"
    REAL_POWER = "real_power"
    LIBRARY = "library"
    GROUP = "group"
    GLOBAL_CONFIGURATION = "global_configuration"


@dataclass(slots=True)
class PowercalcFormStep:
    schema: vol.Schema | Callable[[], Coroutine[Any, Any, vol.Schema | None]]
    step: Step
    validate_user_input: (
        Callable[
            [dict[str, Any]],
            Coroutine[Any, Any, dict[str, Any]],
        ]
        | None
    ) = None

    next_step: Step | Callable[[dict[str, Any]], Coroutine[Any, Any, Step | None]] | None = None
    continue_utility_meter_options_step: bool = False
    continue_advanced_step: bool = False
    form_kwarg: dict[str, Any] | None = None
    form_data: dict[str, Any] | None = None


def fill_schema_defaults(
    data_schema: vol.Schema,
    options: dict[str, Any],
) -> vol.Schema:
    """Make a copy of the schema with suggested values set to saved options."""
    schema = {}
    for key, val in data_schema.schema.items():
        new_key = key
        if key in options and isinstance(key, vol.Marker):
            if isinstance(key, vol.Optional) and callable(key.default) and key.default():
                new_key = vol.Optional(key.schema, default=options.get(key))  # type: ignore
            elif "suggested_value" not in (new_key.description or {}):
                new_key = copy.copy(key)
                new_key.description = {"suggested_value": options.get(key)}  # type: ignore
        schema[new_key] = val
    return vol.Schema(schema)
