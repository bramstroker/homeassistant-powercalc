from __future__ import annotations

from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir, selector
import voluptuous as vol

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_MODEL, CONF_SUB_PROFILE, DOMAIN, ISSUE_COMPOSITE_DEVICE_ID
from custom_components.powercalc.device_binding import is_composite_device_id
from custom_components.powercalc.flow_helper.schema import build_sub_profile_schema
from custom_components.powercalc.power_profile.factory import get_power_profile


class SubProfileRepairFlow(RepairsFlow):
    """Handler for sub profile correction."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._hass = hass

    async def async_step_init(self, _: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""

        return await self.async_step_sub_profile()

    async def async_step_sub_profile(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            new_data = self._config_entry.data.copy()
            new_data[CONF_MODEL] = f"{new_data[CONF_MODEL]}/{user_input[CONF_SUB_PROFILE]}"
            self._hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return self.async_create_entry(title="", data={})  # type: ignore[no-any-return]

        source_entity = create_source_entity(self._config_entry.data[CONF_ENTITY_ID], self._hass)
        profile = await get_power_profile(self.hass, dict(self._config_entry.data), source_entity)
        assert profile
        sub_profile_schema = await build_sub_profile_schema(profile, None)

        remarks = profile.config_flow_sub_profile_remarks
        if remarks:
            remarks = "\n\n" + remarks

        return self.async_show_form(  # type: ignore[no-any-return]
            step_id="sub_profile",
            data_schema=sub_profile_schema,
            description_placeholders={
                "entity_id": source_entity.entity_id,
                "remarks": remarks or "",
                "model": profile.model,
                "manufacturer": profile.manufacturer,
            },
        )


class CompositeDeviceIdRepairFlow(RepairsFlow):
    """Handle selection of a device after Home Assistant split a legacy device."""

    def __init__(self, entry_id: str, entry_title: str) -> None:
        """Initialize the repair flow."""
        self._entry_id = entry_id
        self._entry_title = entry_title

    async def async_step_init(self, _: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        """Handle the first step of the repair flow."""
        return await self.async_step_select_device()

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        """Select a concrete split device, or unlink the Powercalc entities."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is None:
                return self.async_abort(reason="entry_removed")  # type: ignore[no-any-return]

            selected_device_id = user_input.get(CONF_DEVICE)
            if selected_device_id is not None:
                device_reg = dr.async_get(self.hass)
                if (
                    not isinstance(selected_device_id, str)
                    or device_reg.async_get(selected_device_id) is None
                    or is_composite_device_id(self.hass, selected_device_id)
                ):
                    errors["base"] = "invalid_device"

            if not errors:
                new_data = dict(entry.data)
                if selected_device_id is None:
                    new_data.pop(CONF_DEVICE, None)
                else:
                    new_data[CONF_DEVICE] = selected_device_id

                self.hass.config_entries.async_update_entry(entry, data=new_data)
                ir.async_delete_issue(
                    self.hass,
                    DOMAIN,
                    f"{ISSUE_COMPOSITE_DEVICE_ID}_{self._entry_id}",
                )
                await self.hass.config_entries.async_reload(self._entry_id)
                return self.async_create_entry(title="", data={})  # type: ignore[no-any-return]

        return self.async_show_form(  # type: ignore[no-any-return]
            step_id="select_device",
            data_schema=vol.Schema({vol.Optional(CONF_DEVICE): selector.DeviceSelector()}),
            errors=errors,
            description_placeholders={"name": self._entry_title},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    if not data or "config_entry_id" not in data:
        raise ValueError("Missing config entry ID for repair flow")

    config_entry_id = str(data["config_entry_id"])
    config_entry = hass.config_entries.async_get_entry(config_entry_id)
    if issue_id == f"{ISSUE_COMPOSITE_DEVICE_ID}_{config_entry_id}":
        return CompositeDeviceIdRepairFlow(
            config_entry_id,
            config_entry.title if config_entry else "Unknown configuration",
        )

    if config_entry is None:
        raise ValueError(f"Unknown config entry: {config_entry_id}")
    return SubProfileRepairFlow(hass, config_entry)
