import copy
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import voluptuous as vol
from homeassistant.data_entry_flow import FlowResult


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
    UTILITY_METER_OPTIONS = "utility_meter_options"
    GLOBAL_CONFIGURATION = "global_configuration"
    GLOBAL_CONFIGURATION_ENERGY = "global_configuration_energy"
    GLOBAL_CONFIGURATION_UTILITY_METER = "global_configuration_utility_meter"


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


class PowercalcFlow(Protocol):
    hass: Any
    sensor_config: dict[str, Any]
    name: str | None
    selected_sensor_type: str | None

    async def async_set_unique_id(self, unique_id: str) -> None: ...
    def async_show_menu(self, *, step_id: str, menu_options: list[str]) -> FlowResult: ...
    async def handle_form_step(
        self,
        form_step: PowercalcFormStep,
        user_input: dict[str, Any] | None,
    ) -> FlowResult: ...
    def abort_if_unique_id_configured(self) -> None: ...


class PowercalcOptionFlowProtocol(PowercalcFlow, Protocol):
    async def async_handle_options_step(self, user_input: dict[str, Any] | None, schema: vol.Schema, step: Step) -> FlowResult: ...


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
