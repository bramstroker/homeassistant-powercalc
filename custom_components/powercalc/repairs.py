from __future__ import annotations

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_MODEL, CONF_SUB_PROFILE
from custom_components.powercalc.flow_helper.schema import build_sub_profile_schema
from custom_components.powercalc.power_profile.factory import get_power_profile


class SubProfileRepairFlow(RepairsFlow):
    """Handler for sub profile correction."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._hass = hass

    async def async_step_init(
        self,
        user_input: dict[str, str] | None = None,
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""

        return await self.async_step_sub_profile()

    async def async_step_sub_profile(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            new_data = self._config_entry.data.copy()
            new_data[CONF_MODEL] = f"{new_data[CONF_MODEL]}/{user_input[CONF_SUB_PROFILE]}"
            self._hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return self.async_create_entry(title="", data={})

        source_entity = await create_source_entity(self._config_entry.data[CONF_ENTITY_ID], self._hass)
        profile = await get_power_profile(self.hass, dict(self._config_entry.data), source_entity)
        assert profile
        sub_profile_schema = await build_sub_profile_schema(profile, None)

        remarks = profile.config_flow_sub_profile_remarks
        if remarks:
            remarks = "\n\n" + remarks

        return self.async_show_form(
            step_id="sub_profile",
            data_schema=sub_profile_schema,
            description_placeholders={
                "entity_id": source_entity.entity_id,
                "remarks": remarks or "",
                "model": profile.model,
                "manufacturer": profile.manufacturer,
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    assert data
    config_entry_id = str(data["config_entry_id"])
    config_entry = hass.config_entries.async_get_entry(config_entry_id)
    assert config_entry
    return SubProfileRepairFlow(hass, config_entry)
