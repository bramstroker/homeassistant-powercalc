"""Group-related logic for the config flow."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import (
    CONF_DEVICE,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_NAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.helpers.selector import TextSelector
import voluptuous as vol

from custom_components.powercalc.const import (
    CONF_AREA,
    CONF_EXCLUDE_ENTITIES,
    CONF_FLOOR,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_MEMBER_DEVICES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_TRACKED_AUTO,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_HIDE_MEMBERS,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_MAIN_POWER_SENSOR,
    CONF_NEW_GROUP,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    CONF_SUBTRACT_ENTITIES,
    DOMAIN,
    GroupType,
    SensorType,
)
from custom_components.powercalc.flow_helper.common import PowercalcFormStep, Step, fill_schema_defaults
from custom_components.powercalc.flow_helper.schema import SCHEMA_ENERGY_SENSOR_TOGGLE, SCHEMA_UTILITY_METER_TOGGLE
from custom_components.powercalc.group_include.include import find_entities
from custom_components.powercalc.sensors.group.config_entry_utils import get_group_entries
from custom_components.powercalc.sensors.group.tracked_untracked import find_auto_tracked_power_entities
from custom_components.powercalc.sensors.power import PowerSensor

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcCommonFlow, PowercalcConfigFlow, PowercalcOptionsFlow

# Constants
UNIQUE_ID_TRACKED_UNTRACKED = "pc_tracked_untracked"

# Schemas
SCHEMA_GROUP = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_DEVICE): selector.DeviceSelector(),
    },
)

SCHEMA_GROUP_DOMAIN_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_DOMAIN): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["all"] + [cls.value for cls in Platform],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        vol.Optional(CONF_EXCLUDE_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=Platform.SENSOR,
                device_class=[SensorDeviceClass.ENERGY, SensorDeviceClass.POWER],
                multiple=True,
            ),
        ),
    },
)

SCHEMA_GROUP_DOMAIN = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        **SCHEMA_GROUP_DOMAIN_OPTIONS.schema,
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_GROUP_SUBTRACT_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=Platform.SENSOR,
                device_class=SensorDeviceClass.POWER,
                multiple=False,
            ),
        ),
        vol.Optional(CONF_SUBTRACT_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=Platform.SENSOR,
                device_class=SensorDeviceClass.POWER,
                multiple=True,
            ),
        ),
    },
)

SCHEMA_GROUP_SUBTRACT = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        **SCHEMA_GROUP_SUBTRACT_OPTIONS.schema,
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_GROUP_TRACKED_UNTRACKED = vol.Schema(
    {
        vol.Optional(CONF_MAIN_POWER_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=Platform.SENSOR,
                device_class=SensorDeviceClass.POWER,
            ),
        ),
        vol.Required(CONF_GROUP_TRACKED_AUTO): selector.BooleanSelector(),
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_GROUP_TRACKED_UNTRACKED_MANUAL = vol.Schema(
    {
        vol.Required(CONF_GROUP_TRACKED_POWER_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=Platform.SENSOR,
                device_class=SensorDeviceClass.POWER,
                multiple=True,
            ),
        ),
    },
)

MENU_GROUP = [
    Step.GROUP_CUSTOM,
    Step.GROUP_DOMAIN,
    Step.GROUP_SUBTRACT,
    Step.GROUP_TRACKED_UNTRACKED,
]

# Mappings
GROUP_SCHEMAS: dict[GroupType, vol.Schema] = {
    GroupType.CUSTOM: SCHEMA_GROUP,
    GroupType.DOMAIN: SCHEMA_GROUP_DOMAIN,
    GroupType.SUBTRACT: SCHEMA_GROUP_SUBTRACT,
    GroupType.TRACKED_UNTRACKED: SCHEMA_GROUP_TRACKED_UNTRACKED,
}

GROUP_STEP_MAPPING: dict[GroupType, Step] = {
    GroupType.CUSTOM: Step.GROUP_CUSTOM,
    GroupType.DOMAIN: Step.GROUP_DOMAIN,
    GroupType.STANDBY: Step.GROUP_DOMAIN,
    GroupType.SUBTRACT: Step.GROUP_SUBTRACT,
    GroupType.TRACKED_UNTRACKED: Step.GROUP_TRACKED_UNTRACKED,
}


def validate_group_input(user_input: dict[str, Any] | None = None) -> None:
    """Validate the group form."""
    required_keys = {
        CONF_SUB_GROUPS,
        CONF_GROUP_POWER_ENTITIES,
        CONF_GROUP_ENERGY_ENTITIES,
        CONF_GROUP_MEMBER_SENSORS,
        CONF_GROUP_MEMBER_DEVICES,
        CONF_AREA,
        CONF_FLOOR,
    }

    if not any(key in (user_input or {}) for key in required_keys):
        raise SchemaFlowError("group_mandatory")


def create_schema_group_custom(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
    is_option_flow: bool = False,
) -> vol.Schema:
    """Create config schema for groups."""
    member_sensors = [
        selector.SelectOptionDict(value=config_entry.entry_id, label=config_entry.title)
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if config_entry.data.get(CONF_SENSOR_TYPE) in [SensorType.VIRTUAL_POWER, SensorType.REAL_POWER]
        and config_entry.unique_id is not None
        and config_entry.title is not None
    ]
    member_sensor_selector = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=member_sensors,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        ),
    )

    schema = vol.Schema(
        {
            vol.Optional(CONF_GROUP_MEMBER_SENSORS): member_sensor_selector,
            vol.Optional(CONF_GROUP_MEMBER_DEVICES): selector.DeviceSelector(
                selector.DeviceSelectorConfig(
                    multiple=True,
                    entity=selector.EntitySelectorConfig(
                        device_class=[SensorDeviceClass.POWER, SensorDeviceClass.ENERGY],
                    ),
                ),
            ),
            vol.Optional(CONF_GROUP_POWER_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.POWER,
                    multiple=True,
                ),
            ),
            vol.Optional(CONF_GROUP_ENERGY_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.ENERGY,
                    multiple=True,
                ),
            ),
            vol.Optional(CONF_SUB_GROUPS): create_group_selector(hass, current_entry=config_entry),
            vol.Optional(CONF_AREA): selector.AreaSelector(),
            vol.Optional(CONF_FLOOR): selector.FloorSelector(),
            vol.Optional(CONF_DEVICE): selector.DeviceSelector(),
            vol.Optional(CONF_HIDE_MEMBERS, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_INCLUDE_NON_POWERCALC_SENSORS, default=True): selector.BooleanSelector(),
            vol.Optional(CONF_FORCE_CALCULATE_GROUP_ENERGY, default=False): selector.BooleanSelector(),
        },
    )

    if not is_option_flow:
        schema = schema.extend(
            {
                vol.Optional(CONF_GROUP_ENERGY_START_AT_ZERO, default=True): selector.BooleanSelector(),
                **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
                **SCHEMA_UTILITY_METER_TOGGLE.schema,
            },
        )

    return schema


def create_group_selector(
    hass: HomeAssistant,
    current_entry: ConfigEntry | None = None,
    group_entries: list[ConfigEntry] | None = None,
) -> selector.SelectSelector:
    """Create the group selector."""
    options = [
        selector.SelectOptionDict(
            value=config_entry.entry_id,
            label=config_entry.title,
        )
        for config_entry in (group_entries or get_group_entries(hass, GroupType.CUSTOM))
        if current_entry is None or config_entry.entry_id != current_entry.entry_id
    ]

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
        ),
    )


async def create_schema_tracked_untracked_auto(hass: HomeAssistant) -> vol.Schema:
    """Handle the flow for tracked/untracked group sensor."""
    tracked_entities = await find_auto_tracked_power_entities(hass)

    return vol.Schema(
        {
            vol.Optional(CONF_EXCLUDE_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    multiple=True,
                    include_entities=list(tracked_entities),
                ),
            ),
        },
    )


async def create_schema_group_tracked_untracked_manual(
    hass: HomeAssistant,
    user_input: dict[str, Any] | None = None,
    schema: vol.Schema | None = None,
) -> vol.Schema:
    """Handle the flow for tracked/untracked group sensor."""
    if not schema:
        schema = SCHEMA_GROUP_TRACKED_UNTRACKED_MANUAL

    if not user_input:
        result = await find_entities(hass)
        tracked_entities = [entity.entity_id for entity in result.resolved if isinstance(entity, PowerSensor)]
        schema = fill_schema_defaults(schema, {CONF_GROUP_TRACKED_POWER_ENTITIES: tracked_entities})

    return schema


class GroupFlow:
    def __init__(self, flow: PowercalcCommonFlow) -> None:
        self.flow = flow

    async def async_step_assign_groups(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for assigning groups."""
        group_entries = get_group_entries(self.flow.hass, GroupType.CUSTOM)
        if not group_entries:
            return await self.flow.handle_final_steps()

        schema = vol.Schema(
            {
                vol.Optional(CONF_GROUP): create_group_selector(self.flow.hass, group_entries=group_entries),
                vol.Optional(CONF_NEW_GROUP): TextSelector(),
            },
        )

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            groups = user_input.get(CONF_GROUP) or []
            new_group = user_input.get(CONF_NEW_GROUP)
            if new_group:
                groups.append(new_group)
            return {CONF_GROUP: groups}

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.ASSIGN_GROUPS,
                schema=schema,
                continue_advanced_step=True,
                continue_utility_meter_options_step=True,
                validate_user_input=_validate,
            ),
            user_input,
        )


class GroupConfigFlow(GroupFlow):
    """
    Encapsulates all group-related steps for config & options flows.
    Composition-based: call from ConfigFlow/OptionsFlow and delegate here.
    Expects the parent 'flow' to expose:
      - hass
      - sensor_config: dict
      - name: str | None
      - selected_sensor_type: str | None
      - async_set_unique_id(), _abort_if_unique_id_configured()
      - handle_form_step(PowercalcFormStep, user_input) -> FlowResult
      - async_show_menu(...), fill_schema_defaults(...),
      - create_group_selector(...), create_schema_group_custom(...)

    We deliberately keep this controller dumb: it only handles group UX.
    """

    def __init__(self, flow: PowercalcConfigFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcConfigFlow = flow

    async def async_step_menu_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = [Step.GROUP_CUSTOM, Step.GROUP_DOMAIN, Step.GROUP_SUBTRACT, Step.GROUP_TRACKED_UNTRACKED]
        # Hide tracked/untracked if already present
        entry = self.flow.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN,
            UNIQUE_ID_TRACKED_UNTRACKED,
        )
        if entry:
            menu.remove(Step.GROUP_TRACKED_UNTRACKED)
        return self.flow.async_show_menu(step_id=Step.MENU_GROUP, menu_options=menu)

    async def handle_group_step(
        self,
        group_type: GroupType,
        user_input: dict[str, Any] | None = None,
        schema: vol.Schema | None = None,
        next_step: Callable[[dict[str, Any]], Coroutine[Any, Any, Step | None]] | None = None,
    ) -> FlowResult:
        async def _validate(ui: dict[str, Any]) -> dict[str, Any]:
            if group_type == GroupType.CUSTOM:
                validate_group_input(ui)

            self.flow.name = ui.get(CONF_NAME)
            self.flow.sensor_config.update(ui)
            self.flow.sensor_config.update({CONF_GROUP_TYPE: group_type})
            return ui

        self.flow.selected_sensor_type = SensorType.GROUP
        step = GROUP_STEP_MAPPING[group_type]

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=step,
                schema=schema or GROUP_SCHEMAS[group_type],
                validate_user_input=_validate,
                continue_utility_meter_options_step=True,
                next_step=next_step,
            ),
            user_input,
        )

    async def async_step_group_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        schema = SCHEMA_GROUP.extend(create_schema_group_custom(self.flow.hass).schema)
        return await self.handle_group_step(GroupType.CUSTOM, user_input, schema)

    async def async_step_group_domain(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.handle_group_step(GroupType.DOMAIN, user_input)

    async def async_step_group_subtract(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.handle_group_step(GroupType.SUBTRACT, user_input)

    async def async_step_group_tracked_untracked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        await self.flow.async_set_unique_id(UNIQUE_ID_TRACKED_UNTRACKED)
        self.flow.abort_if_unique_id_configured()
        if user_input is not None:
            user_input[CONF_NAME] = "Tracked / Untracked"

        async def _next(ui: dict[str, Any]) -> Step | None:
            return Step.GROUP_TRACKED_UNTRACKED_AUTO if bool(ui.get("group_tracked_auto", True)) else Step.GROUP_TRACKED_UNTRACKED_MANUAL

        return await self.handle_group_step(
            GroupType.TRACKED_UNTRACKED,
            user_input,
            schema=SCHEMA_GROUP_TRACKED_UNTRACKED,
            next_step=_next,
        )

    async def async_step_group_tracked_untracked_auto(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        schema = await create_schema_tracked_untracked_auto(self.flow.hass)
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.GROUP_TRACKED_UNTRACKED_AUTO,
                schema=schema,
                continue_utility_meter_options_step=True,
            ),
            user_input,
        )

    async def async_step_group_tracked_untracked_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        schema = await create_schema_group_tracked_untracked_manual(self.flow.hass, user_input)
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.GROUP_TRACKED_UNTRACKED_MANUAL,
                schema=schema,
                continue_utility_meter_options_step=True,
            ),
            user_input,
        )


class GroupOptionsFlow(GroupFlow):
    """Handle an option flow for PowerCalc."""

    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_group_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        schema = fill_schema_defaults(
            create_schema_group_custom(self.flow.hass, self.flow.config_entry, True),
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.GROUP_CUSTOM)

    async def async_step_group_domain(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        schema = fill_schema_defaults(
            SCHEMA_GROUP_DOMAIN_OPTIONS,
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.GROUP_DOMAIN)

    async def async_step_group_subtract(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        schema = fill_schema_defaults(
            SCHEMA_GROUP_SUBTRACT_OPTIONS,
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.GROUP_SUBTRACT)

    async def async_step_group_tracked_untracked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        schema = fill_schema_defaults(
            SCHEMA_GROUP_TRACKED_UNTRACKED,
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.GROUP_TRACKED_UNTRACKED)

    async def async_step_group_tracked_untracked_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the group options flow."""
        schema = fill_schema_defaults(
            SCHEMA_GROUP_TRACKED_UNTRACKED_MANUAL,
            self.flow.sensor_config,
        )
        return await self.flow.async_handle_options_step(user_input, schema, Step.GROUP_TRACKED_UNTRACKED_MANUAL)

    def build_group_menu(self) -> list[Step]:
        """Build the group menu."""
        group_type = self.flow.sensor_config.get(CONF_GROUP_TYPE, GroupType.CUSTOM)
        if group_type == GroupType.DOMAIN:
            return [Step.GROUP_DOMAIN]
        if group_type == GroupType.SUBTRACT:
            return [Step.GROUP_SUBTRACT]
        if group_type == GroupType.TRACKED_UNTRACKED:
            return [Step.GROUP_TRACKED_UNTRACKED] + (
                [Step.GROUP_TRACKED_UNTRACKED_MANUAL] if not self.flow.sensor_config.get("group_tracked_auto", True) else []
            )
        return [Step.GROUP_CUSTOM]
