from collections.abc import Awaitable, Callable, Coroutine
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
    SUB_PROFILE_PER_DEVICE = "sub_profile_per_device"
    USER = "user"
    SMART_SWITCH = "smart_switch"
    INIT = "init"
    ENERGY_OPTIONS = "energy_options"
    UTILITY_METER_OPTIONS = "utility_meter_options"
    GLOBAL_CONFIGURATION = "global_configuration"
    GLOBAL_CONFIGURATION_DISCOVERY = "global_configuration_discovery"
    GLOBAL_CONFIGURATION_ENERGY = "global_configuration_energy"
    GLOBAL_CONFIGURATION_COST = "global_configuration_cost"
    GLOBAL_CONFIGURATION_THROTTLING = "global_configuration_throttling"
    GLOBAL_CONFIGURATION_UTILITY_METER = "global_configuration_utility_meter"


class FlowType(StrEnum):
    VIRTUAL_POWER = "virtual_power"
    DAILY_ENERGY = "daily_energy"
    REAL_POWER = "real_power"
    LIBRARY = "library"
    GROUP = "group"
    GLOBAL_CONFIGURATION = "global_configuration"


type MaybeAwaitable[R] = R | Awaitable[R]


@dataclass(slots=True)
class PowercalcFormStep:
    schema: vol.Schema | Callable[[], Coroutine[Any, Any, vol.Schema | None]]
    step: Step
    validate_user_input: (
        Callable[
            [dict[str, Any]],
            MaybeAwaitable[dict[str, Any]],
        ]
        | None
    ) = None

    next_step: Step | Callable[[dict[str, Any]], MaybeAwaitable[Step | None]] | None = None
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
                new_key = vol.Optional(key.schema, default=options.get(key))  # type: ignore[call-overload]
            elif isinstance(key, vol.Required):
                new_key = vol.Required(key.schema, default=options.get(key))  # type: ignore[call-overload]
                new_key.description = {"suggested_value": options.get(key)}  # type: ignore[call-overload]
            elif "suggested_value" not in (new_key.description or {}):
                new_key = copy.copy(key)
                new_key.description = {"suggested_value": options.get(key)}  # type: ignore[call-overload]
        schema[new_key] = val
    return vol.Schema(schema)


def unwrap_choose_selector(
    user_input: dict[str, Any],
    wrapper_key: str,
    value_key: str | Callable[[object], str] | None = None,
) -> dict[str, Any]:
    """
    Unwrap a ChooseSelector value in user_input back into flat keys.

    A ChooseSelector value looks like {"active_choice": "<key>", "<key>": <value>}.
    The wrapper key is dropped, and the active choice's value is merged back into user_input.
    Home Assistant schema validation returns the selected value directly; use ``value_key``
    to map that validated value back to a config key.
    """
    if wrapper_key not in user_input:
        return user_input

    raw = user_input.pop(wrapper_key)
    if not isinstance(raw, dict):
        if isinstance(value_key, str):
            user_input[value_key] = raw
        elif value_key is not None:
            user_input[value_key(raw)] = raw
        return user_input

    if "active_choice" not in raw:
        user_input.update(raw)
        return user_input

    active = raw["active_choice"]
    value = raw.get(active)
    if value is None:
        return user_input

    if isinstance(value, dict):
        user_input.update(value)
    else:
        user_input[active] = value
    return user_input


def wrap_choose_selector(
    form_data: dict[str, Any],
    wrapper_key: str,
    choices: dict[str, list[str] | str],
    *,
    raw_value: bool = False,
) -> dict[str, Any]:
    """
    Build the ChooseSelector value for ``wrapper_key`` from existing flat ``form_data``.

    ``choices`` maps the choice id to either a single key (the value of that key becomes
    the choice value) or a list of keys (a dict of those keys becomes the choice value).
    The first choice that has a matching key in form_data is used.
    """
    for choice_id, mapping in choices.items():
        keys = [mapping] if isinstance(mapping, str) else mapping
        present = {key: form_data[key] for key in keys if key in form_data}
        if not present:
            continue

        if isinstance(mapping, str):
            choice_value: Any = present[mapping]
        else:
            choice_value = present

        if raw_value:
            return {**form_data, wrapper_key: choice_value}

        return {**form_data, wrapper_key: {"active_choice": choice_id, choice_id: choice_value}}

    return form_data
