import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.powercalc.const import CONF_SUB_PROFILE
from custom_components.powercalc.power_profile.power_profile import PowerProfile


async def build_sub_profile_schema(
    profile: PowerProfile,
    selected_sub_profile: str | None,
) -> vol.Schema:
    """Create sub profile schema."""
    sub_profiles = [
        selector.SelectOptionDict(
            value=sub_profile[0],
            label=sub_profile[1]["name"] if "name" in sub_profile[1] else sub_profile[0],
        )
        for sub_profile in await profile.get_sub_profiles()
    ]
    return vol.Schema(
        {
            vol.Required(
                CONF_SUB_PROFILE,
                description={"suggested_value": selected_sub_profile},
                default=selected_sub_profile,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sub_profiles,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        },
    )
